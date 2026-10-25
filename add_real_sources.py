#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量实测公开采集站（真实源头层）并入编配置。
用法: python add_real_sources.py
候选写在 CANDIDATES；实测通过(分类抽样有货)才入编 tvbox_config.json 并登记 vod_check.json。
"""
import json
import os
import ssl
import time
import urllib.request
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "tvbox_config.json")
CHECK_PATH = os.path.join(BASE, "deploy", "vod_check.json")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 名称 -> 采集站 API 根地址（真实源头层，量子同层）
CANDIDATES = [
    ("360资源", "https://360zy.com/api.php/provide/vod"),
    ("无尽资源", "https://api.wujinapi.me/api.php/provide/vod"),
    ("天涯资源", "https://tyyszy.com/api.php/provide/vod"),
    ("ikun资源", "https://ikunzyapi.com/api.php/provide/vod"),
    ("闪电资源", "https://sdzyapi.com/api.php/provide/vod"),
    ("U酷资源", "https://api.ukuapi88.com/api.php/provide/vod"),
]


def get(u):
    last = ""
    for proxy in (None, {}):
        try:
            op = urllib.request.build_opener(
                urllib.request.ProxyHandler(proxy),
                urllib.request.HTTPSHandler(context=CTX),
            )
            req = urllib.request.Request(u, headers={"User-Agent": "okhttp/4.9.1"})
            return op.open(req, timeout=12).read().decode("utf-8", "ignore")
        except Exception as e:
            last = str(e)[:50]
    return None


def probe(base):
    """返回 (ok, reason, classes, good, empty)"""
    body = get(base + "?ac=list")
    if not body:
        return False, "接口不可达", [], [], []
    try:
        d = json.loads(body)
    except Exception:
        return False, "返回非JSON", [], [], []
    classes = d.get("class") or []
    if not classes:
        return False, "无分类", [], [], []
    body2 = get(base + "?ac=videolist")
    if not body2:
        return False, "列表接口不可达", classes, [], []
    try:
        d2 = json.loads(body2)
    except Exception:
        return False, "列表返回非JSON", classes, [], []
    if not (d2.get("list") or []):
        return False, "无内容", classes, [], []
    # 分类抽样：每类取前 20 条，total>=5 计有货
    good, empty = [], []
    for c in classes:
        cid, cname = c.get("type_id"), c.get("type_name")
        if cid is None:
            continue
        u = base + "?ac=videolist&t=%s&pg=1" % urllib.parse.quote(str(cid))
        b = get(u)
        total = 0
        if b:
            try:
                total = len(json.loads(b).get("list") or [])
            except Exception:
                total = 0
        (good if total >= 5 else empty).append(
            {"id": cid, "name": cname, "total": total}
        )
        time.sleep(0.3)
    if not good:
        return False, "分类抽样全部为空", classes, good, empty
    return True, "ok", classes, good, empty


def main():
    cfg = json.load(open(CFG_PATH, encoding="utf-8"))
    checks = json.load(open(CHECK_PATH, encoding="utf-8")) if os.path.exists(CHECK_PATH) else []
    existing_keys = {s.get("key") for s in cfg.get("sites", [])}
    existing_names = {s.get("name") for s in cfg.get("sites", [])}
    check_by_key = {c.get("key"): c for c in checks}

    added = []
    for name, base in CANDIDATES:
        if name in existing_names or base in {s.get("api") for s in cfg.get("sites", [])}:
            print("%-6s 已在配置中，跳过" % name)
            continue
        ok, reason, classes, good, empty = probe(base)
        status = "存活" if ok else "剔除(%s)" % reason
        print("%-6s -> %s | 有货分类%d个/空分类%d个" % (name, status, len(good), len(empty)))
        if not ok:
            continue
        key = "Real" + "".join(ch for ch in name if ch.isascii() and ch.isalnum()) or "RealSrc%d" % len(added)
        i = 2
        k0 = key
        while key in existing_keys:
            key = k0 + str(i)
            i += 1
        site = {
            "key": key,
            "name": name,
            "type": 1,
            "api": base,
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
        }
        cfg["sites"].append(site)
        existing_keys.add(key)
        existing_names.add(name)
        check_by_key[key] = {
            "key": key,
            "name": name,
            "ok": True,
            "ms": 0,
            "class_total": len(classes),
            "good": good,
            "empty": empty,
            "reason": "",
        }
        added.append(name)
        time.sleep(0.5)

    if not added:
        print("本次无新增源")
        return
    # vod_check.json 保持原顺序，新条目追加在尾部
    known = set()
    new_checks = []
    for c in checks:
        k = c.get("key")
        if k in check_by_key:
            new_checks.append(check_by_key[k])
            known.add(k)
        else:
            new_checks.append(c)
    for k, c in check_by_key.items():
        if k not in known:
            new_checks.append(c)
    json.dump(cfg, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(new_checks, open(CHECK_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("入编 %d 个源: %s" % (len(added), ", ".join(added)))
    print("当前源总数:", len(cfg["sites"]))


if __name__ == "__main__":
    main()
