#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从活跃的同类仓库收割新的 type=1 采集源，与本配置去重。"""
import json
import os
import re
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(BASE, "deploy")
UA = {"User-Agent": "Mozilla/5.0 Chrome/120.0"}

SOURCES = [
    "https://raw.githubusercontent.com/qist/tvbox/master/dianshi.json",
    "https://raw.githubusercontent.com/qist/tvbox/master/0825.json",
    "https://raw.githubusercontent.com/qist/tvbox/master/0826.json",
    "https://raw.githubusercontent.com/qist/tvbox/master/0827.json",
    "https://raw.githubusercontent.com/xianyuyimu/TVBOX-/main/TVBox/%E4%B8%80%E6%9C%A8cs.json",
    "https://raw.githubusercontent.com/xianyuyimu/TVBOX-/main/TVBox/%E4%B8%80%E6%9C%A8%E8%87%AA%E7%94%A8.json",
    "https://raw.githubusercontent.com/xianyuyimu/TVBOX-/main/TVBox/%E5%A4%87%E7%94%A8.json",
]

# 二期：laoma528/awesome-zhuiju-free（13.4k⭐）每日人工+脚本验证的精选接口，
# 从其 resources.json 动态取 category=tvbox_config 的接口逐个拉取。
# 注意：自动跳过 category 含成人/伦理的条目。
CURATED_LIST = "https://raw.githubusercontent.com/laoma528/awesome-zhuiju-free/main/resources/resources.json"
CURATED_SKIP = ("伦理", "18", "rose", "adult")


def base_api(api):
    a = (api or "").strip()
    return a.split("?")[0] if "?" in a else a


def harvest():
    mine = json.load(open(os.path.join(BASE, "tvbox_config.json"), encoding="utf-8"))
    my_apis = {base_api(s.get("api")).rstrip("/") for s in mine["sites"]}
    my_names = {str(s.get("name")) for s in mine["sites"]}

    found = {}
    for url in SOURCES:
        repo = url.split("/")[4]
        try:
            r = requests.get(url, headers=UA, timeout=15)
            if r.status_code != 200:
                print("[skip] %s: HTTP %d" % (repo, r.status_code))
                continue
            d = r.json()
        except Exception as e:
            print("[skip] %s: %s" % (repo, type(e).__name__))
            continue
        sites = d.get("sites") if isinstance(d, dict) else d
        if not isinstance(sites, list):
            print("[skip] %s: 无 sites" % repo)
            continue
        n = 0
        for s in sites:
            if not isinstance(s, dict):
                continue
            if str(s.get("type")) != "1":
                continue
            api = base_api(s.get("api", "")).rstrip("/")
            if not api.startswith("http"):
                continue
            if api in my_apis:
                continue  # 我们已有
            name = str(s.get("name") or "").strip()
            if name in my_names:
                continue
            if api not in found:
                found[api] = {"name": name, "api": s.get("api"), "from": repo}
                n += 1
        print("[ok] %s: 新增候选 %d" % (repo, n))
    return found


def harvest_curated(found, my_apis, my_names):
    """二期：laoma528 精选接口 → 逐个拉配置 → 收割 type=1。"""
    try:
        r = requests.get(CURATED_LIST, headers=UA, timeout=20)
        d = r.json()
    except Exception as e:
        print("[skip] 精选清单获取失败:", type(e).__name__)
        return
    tvc = [x for x in d.get("resources", []) if x.get("category") == "tvbox_config"]
    total = 0
    for x in tvc:
        name0, url = str(x.get("name") or ""), str(x.get("url") or "")
        low = (name0 + url).lower()
        if any(k in low for k in CURATED_SKIP):
            print("[skip] %s: 成人内容" % name0)
            continue
        try:
            rr = requests.get(url, headers=UA, timeout=15)
            if rr.status_code != 200:
                print("[skip] %s: HTTP %d" % (name0, rr.status_code))
                continue
            cfg = rr.json()
        except Exception as e:
            print("[skip] %s: %s" % (name0, type(e).__name__))
            continue
        sites = cfg.get("sites") if isinstance(cfg, dict) else None
        if not isinstance(sites, list):
            continue
        n = 0
        for s in sites:
            if not isinstance(s, dict) or str(s.get("type")) != "1":
                continue
            api = base_api(s.get("api", "")).rstrip("/")
            if not api.startswith("http") or api in my_apis or api in found:
                continue
            nm = str(s.get("name") or "").strip()
            if nm in my_names:
                continue
            found[api] = {"name": nm, "api": s.get("api"), "from": "精选:" + name0}
            n += 1
        total += n
        if n:
            print("[ok] 精选:%s +%d" % (name0, n))
    print("二期精选合计新增: %d" % total)


if __name__ == "__main__":
    os.makedirs(DEPLOY, exist_ok=True)
    found = harvest()
    # 二期：精选接口（需要 mine 的去重集合）
    mine = json.load(open(os.path.join(BASE, "tvbox_config.json"), encoding="utf-8"))
    my_apis = {base_api(s.get("api")).rstrip("/") for s in mine["sites"]}
    my_names = {str(s.get("name")) for s in mine["sites"]}
    harvest_curated(found, my_apis, my_names)
    print("\n共 %d 个新候选：" % len(found))
    for api, v in sorted(found.items()):
        print("  %-18s [%s] %s" % (v["name"][:18], v["from"][:14], api[:70]))
    json.dump(list(found.values()),
              open(os.path.join(DEPLOY, "_new_candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
