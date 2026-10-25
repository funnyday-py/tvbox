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
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "deploy", "live.txt")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

M3U_SOURCES = [
    ("🛰 综合直播", "http://193.123.86.190:14888/TV/iptv.php"),
    ("🐯 虎牙一起看", "https://sub.ottiptv.cc/huyayqk.m3u"),
    ("🐟 斗鱼一起看", "https://sub.ottiptv.cc/douyuyqk.m3u"),
    ("🎪 YY轮播", "https://sub.ottiptv.cc/yylunbo.m3u"),
]
FALLBACK_TXT = "https://gh-proxy.com/https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt"


def get(u):
    last = ""
    for proxy in (None, {}):
        try:
            op = urllib.request.build_opener(
                urllib.request.ProxyHandler(proxy),
                urllib.request.HTTPSHandler(context=CTX),
            )
            req = urllib.request.Request(u, headers={"User-Agent": "okhttp/4.9.1"})
            return op.open(req, timeout=25).read().decode("utf-8", "ignore")
        except Exception as e:
            last = str(e)[:60]
    print("[warn] 拉取失败 %s: %s" % (u, last))
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
    for gname, url in M3U_SOURCES:
        body = get(url)
        if not body:
            stat.append((gname, 0))
            continue
        groups, order = m3u_to_groups(body, gname)
        n = 0
        for g in order:
            chan = []
            for cname, u in groups[g]:
                if u in seen:
                    continue
                seen.add(u)
                chan.append((cname, u))
            if not chan:
                continue
            out.append("%s,#genre#" % g)
            for cname, u in chan:
                out.append("%s,%s" % (cname, u))
            n += len(chan)
        stat.append((gname, n))

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

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(out) + "\n")
    for g, n in stat:
        print("%-14s %5d 频道" % (g, n))
    print("合计 %d 频道 -> %s" % (sum(n for _, n in stat), OUT))


if __name__ == "__main__":
    main()
