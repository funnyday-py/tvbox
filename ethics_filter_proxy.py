#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TVBox 点播源中转过滤代理

背景：饭太硬/肥猫/王二小等大仓全用 type=3 爬虫源（jar 层控制分类）；
裸 type=1 采集接口的分类列表来自源站 API，TVBox 配置层无法隐藏
（site 级 categories 字段在 TVBoxOSC 源码中只解析不消费，是死字段）。
本服务在 HTTP 中转层把伦理类分类与内容剥掉，让这些优质采集源可以干净接入。

用法：
  python ethics_filter_proxy.py          # 前台运行
  pythonw ethics_filter_proxy.py         # 无窗口运行（开机自启用这个）

电视端配置写法：site 的 api 填 http://192.168.2.201:9979/<路由key>
"""
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlreq
from urllib.error import URLError, HTTPError

HOST = "0.0.0.0"
PORT = 9979
UPSTREAM_TIMEOUT = 30   # 部分采集站（金鹰/极速/火狐）响应慢且不稳，给足超时
RETRIES = 2             # 超时重试次数（采集站间歇性抽风常见）
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 中转路由：本地路径段 -> 上游接口基址
UPSTREAMS = {
    "360":      "https://360zy.com/api.php/provide/vod",
    "jinying":  "https://jyzyapi.com/provide/vod/from/jinyingyun/at/json",
    "jinying2": "https://jyzyapi.com/provide/vod/",
    "jisu":     "https://jszyapi.com/api.php/provide/vod/",
    "huohu":    "https://hhzyapi.com/api.php/provide/vod/",
}

# 分类黑名单：命中的分类连同其内容整个剔除（可按需增删）
ETHICS_RE = re.compile(r"伦理|福利|写真|擦边")

LOG = "%Y-%m-%d %H:%M:%S"


def filter_payload(data):
    """剥掉黑名单分类及其下内容，返回 (过滤后数据, 统计)"""
    stats = {"classes_removed": 0, "videos_removed": 0}
    removed_ids = set()
    classes = data.get("class")
    if isinstance(classes, list):
        kept = []
        for c in classes:
            if ETHICS_RE.search(str(c.get("type_name", ""))):
                removed_ids.add(c.get("type_id"))
                stats["classes_removed"] += 1
            else:
                kept.append(c)
        data["class"] = kept
    lst = data.get("list")
    if isinstance(lst, list):
        kept = []
        for v in lst:
            tn = str(v.get("type_name", ""))
            if ETHICS_RE.search(tn) or v.get("type_id") in removed_ids:
                stats["videos_removed"] += 1
            else:
                kept.append(v)
        data["list"] = kept
    return data, stats


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 静默默认日志，用下面自定义的

    def do_GET(self):
        parts = self.path.lstrip("/").split("?", 1)
        route = parts[0].rstrip("/")
        query = parts[1] if len(parts) > 1 else ""

        if route == "ping":
            self._send_json({"ok": True, "routes": sorted(UPSTREAMS),
                             "filter": ETHICS_RE.pattern, "ts": time.strftime(LOG)})
            return

        upstream = UPSTREAMS.get(route)
        if upstream is None:
            self._send_json({"code": 404, "msg": "unknown route: %s" % route}, 404)
            return

        url = upstream + ("?" + query if query else "")
        t0 = time.time()
        body = None
        last_err = None
        for attempt in range(1, RETRIES + 2):
            try:
                req = urlreq.Request(url, headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/plain,*/*",
                })
                with urlreq.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
                    body = resp.read()
                break
            except (HTTPError, URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt <= RETRIES:
                    print("[%s] %-9s attempt %d fail: %s, retrying"
                          % (time.strftime(LOG), route, attempt, str(e)[:50]))
                    continue
        if body is None:
            print("[%s] %-9s UPSTREAM FAIL %s -> %s"
                  % (time.strftime(LOG), route, url.split("?")[0], str(last_err)[:60]))
            self._send_json({"code": 502, "msg": "upstream fail: %s" % str(last_err)[:80]}, 502)
            return

        ms = int((time.time() - t0) * 1000)
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            # 非 JSON（极端情况）原样透传
            self._send_raw(body, "application/json; charset=utf-8")
            return

        if isinstance(data, dict):
            data, stats = filter_payload(data)
            print("[%s] %-9s %5dms cls-%d vid-%d | %s"
                  % (time.strftime(LOG), route, ms,
                     stats["classes_removed"], stats["videos_removed"], query[:60]))
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send_raw(payload, "application/json; charset=utf-8")
        else:
            self._send_raw(body, "application/json; charset=utf-8")

    def _send_json(self, obj, code=200):
        self._send_raw(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", code)

    def _send_raw(self, payload, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    srv = ThreadingHTTPServer((HOST, PORT), ProxyHandler)
    srv.daemon_threads = True
    print("[%s] TVBox 过滤中转已启动: http://0.0.0.0:%d" % (time.strftime(LOG), PORT))

    for k, v in sorted(UPSTREAMS.items()):
        print("  /%-9s -> %s" % (k, v))

    print("  过滤规则: %s" % ETHICS_RE.pattern)

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("exit", flush=True)


if __name__ == "__main__":
    main()
