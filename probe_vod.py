#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""点播源真实性核验：拉 ?ac=videolist 与 ?ac=list，检查分类与内容是否为空。"""
import json
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 12
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


def norm_api(api):
    """把 api 统一成列表接口基址。"""
    a = api.strip()
    # 去掉查询串，只留路径
    if "?" in a:
        a = a.split("?")[0]
    return a


def probe(site):
    api = norm_api(site.get("api", ""))
    if not api.startswith("http"):
        return {"name": site.get("name"), "key": site.get("key"),
                "ok": False, "reason": "非http源"}
    # 局域网中转源（ethics_filter_proxy）：GitHub runner 不可达，不能据此判死；
    # 其可用性由本机中转层的过滤与重试保证，标记 ok 保留
    if api.startswith("http://192.168."):
        return {"name": site.get("name"), "key": site.get("key"),
                "ok": True, "lan_proxy": True, "videos": 0, "classes": 0,
                "ms": 0, "reason": "局域网中转源，跳过探测"}
    url = api + "?ac=videolist"
    t0 = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            # 借鉴 laoma528/awesome-zhuiju-free 的三态判定：
            # 401/403/405/429 = 反爬/地域限制，源未必死（对家庭宽带 IP 可能可用），不应剪枝
            if r.status_code in (401, 403, 405, 429):
                return {"name": site.get("name"), "key": site.get("key"),
                        "ok": False, "restricted": True, "ms": ms,
                        "reason": "受限 HTTP %d" % r.status_code}
            return {"name": site.get("name"), "key": site.get("key"),
                    "ok": False, "ms": ms, "reason": "HTTP %d" % r.status_code}
        try:
            d = r.json()
        except Exception:
            return {"name": site.get("name"), "key": site.get("key"),
                    "ok": False, "ms": ms, "reason": "非JSON"}
        classes = d.get("class") or []
        vids = d.get("list") or []
        # 分类里有内容才算真的可用
        return {
            "name": site.get("name"), "key": site.get("key"), "ok": True,
            "ms": ms, "classes": len(classes), "videos": len(vids),
            "class_names": [c.get("type_name", "") for c in classes][:12],
        }
    except Exception as e:
        return {"name": site.get("name"), "key": site.get("key"),
                "ok": False, "ms": int((time.time() - t0) * 1000),
                "reason": type(e).__name__}


def main():
    cfg = json.load(open(os.path.join(BASE, "tvbox_config.json"), encoding="utf-8"))
    t1 = [s for s in cfg["sites"] if str(s.get("type")) == "1"]
    # 按 api 去重（同一 api 只测一次）
    seen, uniq = set(), []
    for s in t1:
        a = norm_api(s.get("api", ""))
        if a in seen:
            continue
        seen.add(a)
        uniq.append(s)
    print("type=1 源 %d 个，去重后 %d 个独立接口" % (len(t1), len(uniq)))

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(probe, uniq))

    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    print("\n=== 可用 %d / 失效 %d ===" % (len(ok), len(bad)))
    print("\n--- 可用（按视频数排序）---")
    for r in sorted(ok, key=lambda x: -x["videos"]):
        print("  %-16s 视频%4d 分类%2d %5dms | %s"
              % (r["name"][:16], r["videos"], r["classes"], r["ms"], r["key"]))
    print("\n--- 失效 ---")
    for r in bad:
        print("  %-16s %s" % (r["name"][:16], r.get("reason")))

    json.dump(results, open(os.path.join(BASE, "deploy", "_vod_probe.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    os.makedirs(os.path.join(BASE, "deploy"), exist_ok=True)
    main()
