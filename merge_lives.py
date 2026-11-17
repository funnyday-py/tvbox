#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并可用直播源 -> deploy/live.txt（TVBox txt 格式）。

来源（2026-10-25 实测存活，均不依赖 spider jar）：
  1. 饭太硬综合直播  http://193.123.86.190:14888/TV/iptv.php   (m3u, 带 EPG)
  2. 虎牙一起看      https://sub.ottiptv.cc/huyayqk.m3u
  3. 斗鱼一起看      https://sub.ottiptv.cc/douyuyqk.m3u
  4. YY轮播          https://sub.ottiptv.cc/yylunbo.m3u
  5. gaotianliuyun list.txt（旧央卫视，垫底兜底）

m3u -> TVBox txt：#EXTINF 的 group-title 转 #genre# 分组；缺省组名用来源名。
build_config.py 会把 live.txt 内联进 deploy/tvbox.json 的 lives。
"""
import os
import re
import ssl
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "deploy", "live.txt")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

M3U_SOURCES = [
    ("🛰 综合直播", "http://193.123.86.190:14888/TV/iptv.php", None),
    ("🐯 虎牙一起看", "https://sub.ottiptv.cc/huyayqk.m3u", "虎牙"),
    ("🐟 斗鱼一起看", "https://sub.ottiptv.cc/douyuyqk.m3u", "斗鱼"),
]
# 老电视端内存有限：每组封顶，虎牙/斗鱼组数多必须限制，否则直播页直接 OOM 崩溃
MAX_PER_GROUP = 50     # 单组最多频道数
MAX_PER_SOURCE = 150   # 单来源（虎牙/斗鱼）最多频道数
DROP_GROUPS = {"列表更新时间"}  # YY 测试文件的垃圾组
FALLBACK_TXT = "https://gh-proxy.com/https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt"

# LibreTV 公开 M3U 增量源（组名, 地址）。每源封顶 50 频道，避免老电视端直播页 OOM。
LIBRETV_CAP = 50
LIBRETV_M3U = [
    ("LibreTV·国内电视", "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("LibreTV·港澳台海外", "https://raw.githubusercontent.com/YueChan/Live/main/GNTV.m3u"),
    ("LibreTV·全球体育", "https://iptv-org.github.io/iptv/categories/sports.m3u"),
    ("LibreTV·全球新闻", "https://iptv-org.github.io/iptv/categories/news.m3u"),
    ("LibreTV·全球电影", "https://iptv-org.github.io/iptv/categories/movies.m3u"),
    ("LibreTV·优质精选", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"),
    ("LibreTV·香港频道", "https://iptv-org.github.io/iptv/countries/hk.m3u"),
    ("LibreTV·全球IPTV", "https://iptv-org.github.io/iptv/index.m3u"),
    ("LibreTV·俄罗斯台", "https://gh-proxy.com/https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u"),
]


def get(u, tries=2):
    for i in range(tries):
        last = ""
        for proxy in (None, {}):
            try:
                op = urllib.request.build_opener(
                    urllib.request.ProxyHandler(proxy),
                    urllib.request.HTTPSHandler(context=CTX),
                )
                req = urllib.request.Request(u, headers={"User-Agent": "okhttp/4.9.1"})
                return op.open(req, timeout=20).read().decode("utf-8", "ignore")
            except Exception as e:
                last = str(e)[:60]
        print("[warn] 第%d次拉取失败 %s: %s" % (i + 1, u, last))
        time.sleep(1)
    print("[warn] 放弃 %s" % u)
    return None


def get_lite(u):
    """增量源专用：单次短超时，失败即跳过，不拖慢每日构建。"""
    try:
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=CTX),
        )
        req = urllib.request.Request(u, headers={"User-Agent": "okhttp/4.9.1"})
        return op.open(req, timeout=10).read().decode("utf-8", "ignore")
    except Exception as e:
        print("[warn] LibreTV 增量源跳过: %s" % str(e)[:60])
        return None


def m3u_to_groups(body, default_group):
    """m3u 文本 -> {组名: [(频道名, url), ...]}，保持出现顺序。"""
    groups = {}
    order = []
    group = default_group
    name = None
    for raw in body.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("#EXTINF"):
            m = re.search(r"group-title=\"([^\"]*)\"", raw)
            group = m.group(1).strip() if (m and m.group(1).strip()) else default_group
            t = raw.rsplit(",", 1)
            name = t[1].strip() if len(t) > 1 else None
        elif raw.startswith("#"):
            continue
        elif name:
            if group not in groups:
                groups[group] = []
                order.append(group)
            groups[group].append((name, raw))
            name = None
    return groups, order


def main():
    out = []
    seen = set()
    stat = []
    for gname, url, tag in M3U_SOURCES:
        body = get(url)
        if not body:
            stat.append((gname, 0))
            continue
        groups, order = m3u_to_groups(body, gname)
        n_src = 0
        for g in order:
            if g in DROP_GROUPS or n_src >= MAX_PER_SOURCE:
                break
            chan = []
            for cname, u in groups[g]:
                if u in seen or len(chan) >= MAX_PER_GROUP:
                    continue
                seen.add(u)
                chan.append((cname, u))
            if not chan:
                continue
            # 加来源前缀，避免虎牙/斗鱼出现同名组互相顶掉
            out_g = ("%s·%s" % (tag, g)) if tag else g
            out.append("%s,#genre#" % out_g)
            for cname, u in chan:
                out.append("%s,%s" % (cname, u))
            n_src += len(chan)
        stat.append((gname, n_src))

    # 旧央卫视垫底（本身就是 TVBox txt 格式，原样追加）
    fb = get(FALLBACK_TXT)
    n_fb = 0
    if fb:
        for raw in fb.splitlines():
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                out.append(raw)
                if not raw.endswith("#genre#"):
                    n_fb += 1
    stat.append(("旧·央卫视(垫底)", n_fb))

    # LibreTV 增量：每日拉取公开 M3U 并限流，任一源失败只跳过该源。
    n_ltv = 0
    for tag, url in LIBRETV_M3U:
        body = get_lite(url)
        if not body:
            continue
        groups, order = m3u_to_groups(body, tag)
        chan = []
        for g in order:
            for cname, u in groups[g]:
                if u in seen or not cname or "," in cname:
                    continue
                seen.add(u)
                chan.append((cname, u))
                if len(chan) >= LIBRETV_CAP:
                    break
            if len(chan) >= LIBRETV_CAP:
                break
        if chan:
            out.append("%s,#genre#" % tag)
            for cname, u in chan:
                out.append("%s,%s" % (cname, u))
            n_ltv += len(chan)
    stat.append(("LibreTV·增量", n_ltv))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(out) + "\n")
    for g, n in stat:
        print("%-14s %5d 频道" % (g, n))
    print("合计 %d 频道 -> %s" % (sum(n for _, n in stat), OUT))


if __name__ == "__main__":
    main()
