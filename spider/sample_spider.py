# sample_spider.py
# 示例 TVBox py 爬虫，用于验证调试台功能。
# 真实接入时，把你的爬虫按相同函数签名替换本文件即可（用 SPIDER_PATH 指向它）。
#
# 标准接口（TVBox / CatVod 系 Python 爬虫通用）：
#   init(ext)                  -> str
#   homeContent()              -> {"class":[{type_id,type_name}], "list":[{vod_id,vod_name,vod_pic,vod_remarks}]}
#   categoryContent(tid,pg,filter,ext) -> {"list":[...], "page":, "pagecount":, "total":, "limit":}
#   detailContent(ids)         -> {"list":[{vod_id, vod_name, vod_play_from, vod_play_url, ...}]}
#   searchContent(key, quick)  -> {"list":[...]}
#   playerContent(flag, id)    -> {"playUrl":"", "url":"直链", "header":{...}}
#
# 注意：vod_play_url 中“集”用 # 分隔，“线路”用 $$$ 分隔，单集格式为 集名$url。

def init(ext):
    return ''


_CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "3", "type_name": "综艺"},
]

# 公开测试用 HLS 流（验直链 / 防盗链用，无需自带视频素材）
_TEST_M3U8 = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"


def homeContent():
    return {
        "class": _CLASSES,
        "list": [
            {"vod_id": "m1", "vod_name": "测试电影 A", "vod_pic": "https://picsum.photos/seed/a/300/420",
             "vod_remarks": "1080P"},
            {"vod_id": "m2", "vod_name": "测试电影 B", "vod_pic": "https://picsum.photos/seed/b/300/420",
             "vod_remarks": "4K"},
            {"vod_id": "t1", "vod_name": "测试剧集 C", "vod_pic": "https://picsum.photos/seed/c/300/420",
             "vod_remarks": "更新至12集"},
        ],
    }


def categoryContent(cateId, pg, filter, ext):
    items = []
    for i in range(1, 13):
        items.append({
            "vod_id": f"{cateId}_{i}",
            "vod_name": f"分类{cateId} 影片 {i}",
            "vod_pic": f"https://picsum.photos/seed/{cateId}{i}/300/420",
            "vod_remarks": "HD",
        })
    return {"list": items, "page": int(pg), "pagecount": 5, "total": 60, "limit": 12}


def detailContent(ids):
    vid = ids[0] if ids else "m1"
    # 6 集，集数用 # 分隔；多线路用 $$$ 分隔
    eps = "#".join([
        f"第{i}集${_TEST_M3U8}" for i in range(1, 7)
    ])
    return {"list": [{
        "vod_id": vid,
        "vod_name": "测试详情 " + vid,
        "vod_pic": "https://picsum.photos/seed/detail/300/420",
        "vod_play_from": "默认线路",
        "vod_play_url": eps,
        "vod_content": "这是调试台示例详情，用于验证「海报墙 → 详情 → 选集 → HLS 播放」的闭环。",
    }]}


def searchContent(key, quick):
    return {"list": [
        {"vod_id": "s1", "vod_name": f"搜索:{key} 结果1", "vod_pic": "https://picsum.photos/seed/s1/300/420",
         "vod_remarks": "搜索"},
        {"vod_id": "s2", "vod_name": f"搜索:{key} 结果2", "vod_pic": "https://picsum.photos/seed/s2/300/420",
         "vod_remarks": "搜索"},
    ]}


def playerContent(flag, id):
    # 返回直链与请求头，用于防盗链验证
    return {
        "playUrl": "",
        "url": _TEST_M3U8,
        "header": {"Referer": "https://example.com/", "User-Agent": "Mozilla/5.0"},
    }
