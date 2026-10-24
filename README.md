# TVBox 配置 · 每日自动更新

由 GitHub Actions 每天（北京时间 04:10）自动：刷新直播源 → 更新 spider jar → 实测点播源剔除失效项 → 重建配置并提交。

## 电视端填这个地址

在 TVBox / 影视仓等空壳的「配置地址」里填（**推荐第 1 条，国内实测可达**）：

1. `https://gh-proxy.com/https://raw.githubusercontent.com/funnyday-py/tvbox/main/deploy/tvbox.json`
2. `https://ghproxy.net/https://raw.githubusercontent.com/funnyday-py/tvbox/main/deploy/tvbox.json`
3. `https://cdn.jsdelivr.net/gh/funnyday-py/tvbox@main/deploy/tvbox.json`（jsdelivr 有约 12h 缓存）

> `raw.githubusercontent.com` 直连在国内多数网络不可达，不要直接填。

## 怎么"刷新"

TVBox 空壳不会定时自动刷新，但**每次冷启动（杀进程重开）都会重新拉配置地址**。
所以：每天 Actions 推送新配置后，电视上重启一下 App 即拿到最新版；也可在 设置→配置地址 里手动重刷。

## 当前内容（2026-10-24）

| 项 | 状态 |
|---|---|
| 点播源 | 443（已剔除 14 个实测失效；js 源 269 个已改写为 ghfast 镜像，消除 jsdelivr 单点） |
| 直播 | 96 频道 / 202 线路（CCTV 27 / 卫视 29 / 精品 40，移动 IPTV 直连） |
| spider | gaotianliuyun custom_spider.jar（266777B，md5 41c87635…，走 gh-proxy 分发） |

## 关于「分类点进去是空的」

实测结论：采集站的「电影片 / 电视剧 / 连续剧」一级分类多为空壳，真实内容在「动作片 / 国产剧 / 喜剧片」等二级分类。这是源站数据结构问题，非配置错误。全网统计见 `deploy/vod_check.json`。

## 文件说明

```
deploy/tvbox.json     ← 电视端最终订阅的配置（自动生成，勿手改）
deploy/live.txt       ← 直播源原始 txt（自动刷新）
deploy/spider.jar     ← 本地 jar 备份（远端 403 时可用）
build_config.py       ← 构建脚本（补 spider / 换直播 / 镜像改写 / 剪枝）
probe_vod.py          ← 点播源实测（结果供剪枝）
check_vod_classes.py  ← 分类体检（统计空分类）
.github/workflows/daily.yml ← 每日自动化
```

## 本地手动更新

```bash
python probe_vod.py          # 实测点播源
python build_config.py --check   # 重建并校验
```
