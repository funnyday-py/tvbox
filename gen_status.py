#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成源健康看板，自动写进 README 的标记区段（借鉴 laoma528/awesome-zhuiju-free）。"""
import json
import os
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(BASE, "deploy")
README = os.path.join(BASE, "README.md")
MARK_START = "<!-- TVBOX-STATUS:START -->"
MARK_END = "<!-- TVBOX-STATUS:END -->"
CST = timezone(timedelta(hours=8))


def load(name):
    p = os.path.join(DEPLOY, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    probe = load("_vod_probe.json") or []
    cfg = load("tvbox.json") or {}
    check = load("vod_check.json") or []

    alive = [r for r in probe if r.get("ok")]
    restricted = [r for r in probe if not r.get("ok") and r.get("restricted")]
    dead = [r for r in probe if not r.get("ok") and not r.get("restricted")]
    lives = cfg.get("lives") or []
    ch = sum(len(g.get("channels", [])) for g in lives)
    urls = sum(len(c.get("urls", [])) for g in lives for c in g.get("channels", []))

    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [
        MARK_START,
        "## 源健康看板",
        "",
        "> 🤖 每天由 GitHub Actions 自动检测并更新本节（北京时间 %s）" % now,
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 点播源总数 | %d |" % len(cfg.get("sites", [])),
        "| 实测在线 | %d |" % len(alive),
        "| 🟡 受限（反爬，保留不删） | %d |" % len(restricted),
        "| 🔴 失效（已自动剪除） | %d |" % len(dead),
        "| 直播频道 | %d 频道 / %d 线路 |" % (ch, urls),
        "",
    ]

    if restricted:
        lines.append("**🟡 受限源（不参与剪枝）**：%s"
                     % "、".join(str(r.get("name")) for r in restricted[:15]))
        lines.append("")

    if dead:
        lines += ["**🔴 今日剪除**：", "",
                  "| 源 | 原因 |", "|---|---|"]
        for r in dead[:25]:
            lines.append("| %s | %s |" % (r.get("name"), (r.get("reason") or "")[:40]))
        if len(dead) > 25:
            lines.append("| …共 %d 个 | |" % len(dead))
        lines.append("")

    healthy = sorted((r for r in check if r.get("ok")),
                     key=lambda x: -len(x.get("good", [])))[:5]
    if healthy:
        lines += ["**🟢 分类最健康的前 5 个采集源**（首页默认源取第 1 名）：", ""]
        for r in healthy:
            lines.append("- %s — %d 个分类有内容，共 %d 部"
                         % (r.get("name"), len(r.get("good", [])),
                            sum(c["total"] for c in r.get("good", []))))

    block = "\n".join(lines)

    if os.path.exists(README):
        txt = open(README, encoding="utf-8").read()
        if MARK_START in txt and MARK_END in txt:
            pre = txt[:txt.index(MARK_START)]
            post = txt[txt.index(MARK_END) + len(MARK_END):]
            txt = pre + block + post
        else:
            txt = txt.rstrip() + "\n\n" + block + "\n"
        open(README, "w", encoding="utf-8").write(txt)
        print("README 已更新（%d 在线 / %d 受限 / %d 失效）"
              % (len(alive), len(restricted), len(dead)))
    else:
        print(block)


if __name__ == "__main__":
    main()
