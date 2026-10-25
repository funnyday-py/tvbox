#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""实测新候选采集源，可用的加入 tvbox_config.json 并登记进 vod_check.json（参与健康排序）。"""
import json
import os
import time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(BASE, "deploy")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
DIRECT = requests.Session()
DIRECT.trust_env = False


def get_json(url, tries=2):
    last = None
    for i in range(tries):
        for sess in (requests, DIRECT):
            try:
                r = sess.get(url, headers=UA, timeout=12, verify=False)
                if r.status_code != 200:
                    last = "HTTP %d" % r.status_code
                    continue
                return r.json(), None
            except Exception as e:
                last = type(e).__name__
        time.sleep(0.4)
    return None, last


def key_from_name(name):
    s = "".join(c for c in name if c.isascii() and c.isalnum())
    return s or "New" + str(abs(hash(name)) % 10000)


def main():
    cands = json.load(open(os.path.join(DEPLOY, "_new_candidates.json"), encoding="utf-8"))
    mine = json.load(open(os.path.join(BASE, "tvbox_config.json"), encoding="utf-8"))
    checks = json.load(open(os.path.join(DEPLOY, "vod_check.json"), encoding="utf-8"))

    my_keys = {s.get("key") for s in mine["sites"]}
    added, results = [], []
    for c in cands:
        api = str(c["api"]).rstrip("/")
        base = api.split("?")[0]
        # 1) 拉内容
        d, err = get_json(base + "/?ac=videolist")
        if not d or not (d.get("list") or []):
            print("✗ %-14s %s" % (c["name"], err or "无内容"))
            continue
        vids = len(d.get("list") or [])
        # 2) 拉分类树算健康度
        good = []
        head, e2 = get_json(base + "/?ac=list")
        classes = (head or {}).get("class") or []
        for cl in classes[:8]:
            tid = cl.get("type_id")
            dd, _ = get_json("%s/?ac=videolist&t=%s&pg=1" % (base, tid), tries=1)
            if dd:
                total = dd.get("total") or len(dd.get("list") or [])
                if isinstance(total, int) and total >= 5:
                    good.append({"id": tid, "name": cl.get("type_name", ""), "total": total})
        status = "✓" if good else "△"
        print("%s %-14s 视频%3d 分类%d/%d" % (status, c["name"], vids, len(good), len(classes)))

        key = key_from_name(c["name"]) or None
        while not key or key in my_keys:
            key = (key or "New") + "1"
        my_keys.add(key)
        site = {"key": key, "name": c["name"], "type": 1, "api": api,
                "searchable": 1, "quickSearch": 1, "filterable": 1}
        added.append(site)
        results.append({"key": key, "name": c["name"], "ok": bool(good),
                        "ms": 0, "class_total": len(classes),
                        "good": good, "empty": [], "reason": "" if good else "分类抽样为空"})

    if added:
        mine["sites"].extend(added)
        json.dump(mine, open(os.path.join(BASE, "tvbox_config.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        checks.extend(results)
        json.dump(checks, open(os.path.join(DEPLOY, "vod_check.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n入编 %d 个新源，配置现 %d 源" % (len(added), len(mine["sites"])))


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
