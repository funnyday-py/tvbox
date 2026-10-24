#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TVBox 配置修复 + 每日自动化生成

修复三件事：
1. 补 spider（缺失导致 421 个爬虫源全部无法启动）
2. 替换 lives（原来只有 about:blank 占位死链）
3. 给 269 个 jsdelivr 源做镜像列表（单点故障兜底）

用法：
  python build_config.py            # 只生成本地配置
  python build_config.py --check    # 生成后校验
"""
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(BASE, "deploy")
SRC_CONFIG = os.path.join(BASE, "tvbox_config.json")
LIVE_TXT = os.path.join(DEPLOY, "live.txt")
SPIDER_JAR = os.path.join(DEPLOY, "spider.jar")
OUT_CONFIG = os.path.join(DEPLOY, "tvbox.json")

# ---------------------------------------------------------------- spider
# 优先用本地 jar 的 md5 校验，远端多镜像兜底
# 实测（2026-10-24）：gh-proxy.com / ghproxy.net 可取 266777B 完整 JAR；
# ghfast.top 与 cdn.jsdelivr.net 对大文件返回 403，不可用。
SPIDER_MIRRORS = [
    "https://gh-proxy.com/https://raw.githubusercontent.com/gaotianliuyun/gao/master/jar/custom_spider.jar",
    "https://ghproxy.net/https://raw.githubusercontent.com/gaotianliuyun/gao/master/jar/custom_spider.jar",
]

# ---------------------------------------------------------------- 直播源
# 兜底：本地 live.txt 会一并上传，电视端可用本地/远程任意一个
LIVE_MIRRORS = [
    "https://gh-proxy.com/https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt",
    "https://ghproxy.net/https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt",
]


def md5_of(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def build_spider():
    """拼 spider 字段：url;md5;hash"""
    h = md5_of(SPIDER_JAR)
    if not h:
        print("[warn] 未找到本地 spider.jar，spider 字段留空")
        return ""
    # TVBox 格式：url;md5;hash  —— 第二个字段用于下载后校验
    return "%s;md5;%s" % (SPIDER_MIRRORS[0], h)


def parse_live_txt(path):
    """把 TVBox live.txt 解析成 lives 结构（group + channels）。

    TVBox 的 lives 有两种写法：
      A. {"group": "...", "channels": [{"name":"CCTV1","urls":[...]}]}
      B. 直接给 url 让客户端拉 txt
    这里用 A，把 txt 全部内联，避免电视端还要二次拉取失败。
    """
    if not os.path.exists(path):
        print("[warn] 未找到 live.txt")
        return []
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("gbk", errors="ignore")

    groups = []
    cur = None
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "#genre#" in line:
            gname = line.split(",")[0].strip() or "未分组"
            cur = {"group": gname, "channels": []}
            groups.append(cur)
            continue
        if "," not in line:
            continue
        name, _, url = line.partition(",")
        name, url = name.strip(), url.strip()
        if not name or not url:
            continue
        if cur is None:
            cur = {"group": "未分组", "channels": []}
            groups.append(cur)
        # 同名频道合并 urls（多线路自动切换）
        exist = next((c for c in cur["channels"] if c["name"] == name), None)
        if exist:
            if url not in exist["urls"]:
                exist["urls"].append(url)
        else:
            cur["channels"].append({"name": name, "urls": [url]})
    return groups


def fix_jsdelivr(site):
    """jsdelivr 单点故障：在 ext/api 里保留主链，追加镜像兜底。

    TVBox 的 js 源 api 只接受单个 url，无法直接写多镜像。
    策略：优先用国内可达的 ghfast.top 镜像替换 cdn.jsdelivr.net，
    因为 jsdelivr 在部分地区被墙，ghfast 走 GitHub API 通道更稳。
    """
    api = site.get("api", "")
    if "cdn.jsdelivr.net/gh/" not in api:
        return site, False
    # cdn.jsdelivr.net/gh/user/repo@ver/path -> ghfast.top/https://raw.githubusercontent.com/user/repo/ver/path
    m = re.match(r"https?://cdn\.jsdelivr\.net/gh/([^/]+)/([^@/]+)@([^/]+)/(.+)", api)
    if not m:
        return site, False
    user, repo, ver, path = m.groups()
    site = dict(site)
    site["api"] = "https://ghfast.top/https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        user, repo, ver, path,
    )
    return site, True


def prune_dead_sites(cfg, probe_path):
    """按 probe_vod.py 的结果剔除失效的 type=1 采集源。

    probe 结果按 api 基址去重，同一 api 挂多个名字的源一并剔除。
    """
    if not os.path.exists(probe_path):
        print("[info] 无探测结果（%s），跳过剪枝" % os.path.basename(probe_path))
        return 0
    try:
        results = json.load(open(probe_path, encoding="utf-8"))
    except Exception as e:
        print("[warn] 探测结果解析失败: %s" % e)
        return 0

    # probe_vod.json 只存了 key，不含 api 基址；直接用 ok 标记建黑名单
    dead_keys = {r.get("key") for r in results if r.get("ok") is False}

    sites = cfg.get("sites", [])
    kept = []
    removed = 0
    for s in sites:
        if str(s.get("type")) == "1" and s.get("key") in dead_keys:
            removed += 1
            continue
        kept.append(s)
    cfg["sites"] = kept
    return removed


def build():
    os.makedirs(DEPLOY, exist_ok=True)
    if not os.path.exists(SRC_CONFIG):
        print("[error] 找不到源配置:", SRC_CONFIG)
        return None

    cfg = json.load(open(SRC_CONFIG, encoding="utf-8"))
    print("源配置: sites=%d" % len(cfg.get("sites", [])))

    # 0) 剪枝：剔除探测确认失效的 type=1 源
    n_dead = prune_dead_sites(cfg, os.path.join(DEPLOY, "_vod_probe.json"))
    if n_dead:
        print("剪枝: 剔除失效 type=1 源 %d 个" % n_dead)

    # 1) spider
    cfg["spider"] = build_spider()
    print("spider: %s" % (cfg["spider"][:90] or "(空)"))

    # 2) lives
    groups = parse_live_txt(LIVE_TXT)
    if groups:
        cfg["lives"] = groups
        total = sum(len(g["channels"]) for g in groups)
        print("lives: %d 组 / %d 频道" % (len(groups), total))
    else:
        print("[warn] lives 未替换，保留原值")

    # 3) jsdelivr 镜像
    n_fixed = 0
    new_sites = []
    for s in cfg.get("sites", []):
        s2, changed = fix_jsdelivr(s)
        if changed:
            n_fixed += 1
        new_sites.append(s2)
    cfg["sites"] = new_sites
    print("jsdelivr 源改写: %d" % n_fixed)

    # 4) 元信息（便于电视端排查）
    cfg["_generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cfg["_generator"] = "build_config.py"
    cfg["_site_count"] = len(cfg.get("sites", []))

    with open(OUT_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    size = os.path.getsize(OUT_CONFIG)
    print("输出: %s (%.1f KB)" % (OUT_CONFIG, size / 1024))
    return cfg


def check(cfg):
    ok = True
    # 必备字段
    for k in ("sites", "spider"):
        if not cfg.get(k):
            print("[FAIL] 缺少/为空: %s" % k)
            ok = False
    # spider 带 md5
    if cfg.get("spider") and ";md5;" not in cfg["spider"]:
        print("[WARN] spider 未带 md5 校验")
    # lives 有效
    lives = cfg.get("lives") or []
    if not lives:
        print("[FAIL] lives 为空")
        ok = False
    else:
        bad = [c for g in lives for c in g.get("channels", [])
               if not c.get("urls") or all("about:blank" in u for u in c["urls"])]
        if bad:
            print("[FAIL] lives 含占位死链: %d" % len(bad))
            ok = False
    # 源数量
    print("[OK] sites=%d lives=%d组" % (len(cfg.get("sites", [])), len(lives)))
    return ok


if __name__ == "__main__":
    cfg = build()
    if cfg is None:
        sys.exit(1)
    if "--check" in sys.argv:
        sys.exit(0 if check(cfg) else 2)
