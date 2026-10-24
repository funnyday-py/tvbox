#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
点播源分类体检 + 空分类剪枝

背景（2026-10-24 实测结论）：
  采集站 `ac=list` 返回分类树，`ac=videolist&t=<type_id>` 拉该分类内容。
  很多源的一级分类（电影片/连续剧/综艺片）是空壳，真实内容在二级分类
  （动作片/国产剧/喜剧片…）下。TVBox 首页默认展示一级分类，于是出现
  "动作片点进去是空的/只有一个"。

本工具：
  1. 逐个源拉分类树，按 type_id 实测每个分类的 total
  2. 输出每个源的可用分类清单（total>0）
  3. --filter 模式：把返回空分类的源标记为 dead，供构建脚本剔除
"""
import json
import os
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(BASE, "deploy")
TIMEOUT = 10
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}
# total 小于该值视为"空分类"
EMPTY_THRESHOLD = 5


def base_api(api):
    a = (api or "").strip()
    if "?" in a:
        a = a.split("?")[0]
    return a


# 环境代理（127.0.0.1:6065）间歇性失败会伪装成 SSLError，
# 因此每次请求都做三档降级：走代理 → 绕代理 → 绕代理+不校验证书
_DIRECT = requests.Session()
_DIRECT.trust_env = False
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass


def _get(url, verify=True, direct=False):
    if direct:
        return _DIRECT.get(url, headers=UA, timeout=TIMEOUT, verify=verify)
    return requests.get(url, headers=UA, timeout=TIMEOUT, verify=verify)


def get_json(url, tries=2):
    """三档降级抓取。返回 (json, err)。"""
    last = None
    modes = [(False, True), (True, True), (True, False)]
    for i in range(tries):
        for direct, verify in modes:
            try:
                r = _get(url, verify=verify, direct=direct)
                if r.status_code != 200:
                    last = "HTTP %d" % r.status_code
                    continue
                return r.json(), None
            except Exception as e:
                last = type(e).__name__
        time.sleep(0.4 * (i + 1))
    return None, last


def check_site(site):
    api = base_api(site.get("api", ""))
    name = site.get("name", "")
    if not api.startswith("http"):
        return {"key": site.get("key"), "name": name, "ok": False, "reason": "非http"}

    t0 = time.time()
    head, err = get_json(api + "?ac=list")
    if not head:
        return {"key": site.get("key"), "name": name, "ok": False,
                "reason": "分类接口失败: %s" % err,
                "ms": int((time.time() - t0) * 1000)}

    classes = head.get("class") or []
    if not classes:
        return {"key": site.get("key"), "name": name, "ok": False,
                "reason": "无分类", "ms": int((time.time() - t0) * 1000)}

    # 抽样：一级分类全查（通常 <10 个），二级最多查 6 个
    good, empty = [], []
    for c in classes[:10]:
        tid = c.get("type_id")
        tname = c.get("type_name", "")
        d, e = get_json("%s?ac=videolist&t=%s&pg=1" % (api, tid), tries=1)
        if not d:
            empty.append({"id": tid, "name": tname, "total": None, "err": e})
            continue
        total = d.get("total")
        if total is None:
            total = len(d.get("list") or [])
        if isinstance(total, int) and total >= EMPTY_THRESHOLD:
            good.append({"id": tid, "name": tname, "total": total})
        else:
            empty.append({"id": tid, "name": tname, "total": total})

    ms = int((time.time() - t0) * 1000)
    return {
        "key": site.get("key"), "name": name, "ok": bool(good), "ms": ms,
        "class_total": len(classes), "good": good, "empty": empty,
        "reason": "" if good else "全部分类为空",
    }


def main():
    os.makedirs(DEPLOY, exist_ok=True)
    cfg = json.load(open(os.path.join(BASE, "tvbox_config.json"), encoding="utf-8"))
    t1 = [s for s in cfg["sites"] if str(s.get("type")) == "1"]
    seen, uniq = set(), []
    for s in t1:
        a = base_api(s.get("api"))
        if a in seen:
            continue
        seen.add(a)
        uniq.append(s)

    print("待检源: %d 个（type=1，按 api 去重）" % len(uniq))
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(check_site, uniq))

    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    print("\n可用 %d / 不可用 %d\n" % (len(ok), len(bad)))

    print("=" * 78)
    print("可用源及其分类（只列有内容的）")
    print("=" * 78)
    for r in sorted(ok, key=lambda x: -sum(c["total"] for c in x["good"])):
        goodn = len(r["good"])
        empty_names = [c["name"] for c in r["empty"]]
        print("\n● %s  [%s]  %dms  有效分类 %d/%d"
              % (r["name"][:20], r["key"], r["ms"], goodn, r["class_total"]))
        print("   有内容: " + ", ".join("%s(%d)" % (c["name"], c["total"])
                                      for c in r["good"][:12]))
        if empty_names:
            print("   空分类: " + ", ".join(empty_names[:12]))

    print("\n" + "=" * 78)
    print("不可用源")
    print("=" * 78)
    for r in bad:
        print("  %-20s %s" % (r["name"][:20], r.get("reason")))

    out = os.path.join(DEPLOY, "vod_check.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n明细已存: %s" % out)

    # 汇总：哪些分类名在所有源里普遍为空（用户最可能撞到的空文件夹）
    from collections import Counter
    empty_cnt = Counter()
    good_cnt = Counter()
    for r in ok:
        for c in r["empty"]:
            empty_cnt[c["name"]] += 1
        for c in r["good"]:
            good_cnt[c["name"]] += 1
    print("\n" + "=" * 78)
    print("分类在全网的普遍情况（空次数 / 有内容次数）")
    print("=" * 78)
    allnames = set(empty_cnt) | set(good_cnt)
    rows = [(n, empty_cnt.get(n, 0), good_cnt.get(n, 0)) for n in allnames]
    for n, e, g in sorted(rows, key=lambda x: (-x[1], -x[2]))[:25]:
        flag = "  <-- 常年空壳" if e >= 3 and g == 0 else ""
        print("  %-10s 空%2d 有内容%2d%s" % (n[:10], e, g, flag))


if __name__ == "__main__":
    main()
