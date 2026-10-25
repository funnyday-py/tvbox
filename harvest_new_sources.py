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


if __name__ == "__main__":
    os.makedirs(DEPLOY, exist_ok=True)
    found = harvest()
    print("\n共 %d 个新候选：" % len(found))
    for api, v in sorted(found.items()):
        print("  %-18s %s" % (v["name"][:18], api[:80]))
    json.dump(list(found.values()),
              open(os.path.join(DEPLOY, "_new_candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
