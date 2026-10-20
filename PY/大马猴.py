# -*- coding: utf-8 -*-
# @name 大马猴影视
# @description 影视站：https://dmhyy.com ，JSON 接口，支持分类、搜索、聚合线路详情与直链/解码播放
# @version 1.0.0
# @downloadURL https://gh-proxy.org/https://github.com/Silent1566/OmniBox-Spider/raw/refs/heads/main/影视/采集/big.py

# =============================================================================
# 大马猴影视（https://dmhyy.com）
#
# 接口：
# - 分类：/api.php/web/filter/vod?type_id=23/22/24/25&page=1&sort=hits
# - 详情：/api.php/web/vod/get_detail?vod_id=xxx
# - 聚合线路：/api.php/web/internal/search_aggregate?vod_id=xxx（优先提取 m3u8 直链）
# - 搜索：/api.php/web/search/index?wd=xxx&page=1
# - 解码：/api.php/web/decode/url?url=xxx
#
# 说明：
# - 分类接口会混入其它分类，脚本内按真实 type_id/type_name 二次过滤
# - 聚合线路必须带 /play/<vid> Referer 与 x-platform 头
#
# 环境变量：
# - DMHY_HOST：站点地址（默认 https://dmhyy.com）
# - DMHY_WEB_SIGN：web-sign 请求头（可选，大马猴当前不需要，云朵站需要）
# =============================================================================

import json
import os
import re
from html import unescape as html_unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlencode

import urllib.error
import urllib.request

try:
    from spider_runner import OmniBox, run
except ImportError:
    # 本地调试兜底：模块缺失时不至于直接崩掉，生产环境仍以正式 spider_runner 为准
    class _FallbackOmniBox:
        @staticmethod
        async def log(level, message):
            print(f"[{level}] {message}")

        @staticmethod
        async def request(url, options=None):
            options = options or {}
            headers = options.get("headers") or {}
            method = str(options.get("method") or "GET").upper()
            timeout = int(options.get("timeout") or 15000) / 1000
            request_obj = urllib.request.Request(url, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request_obj, timeout=timeout) as resp:
                    return {
                        "statusCode": resp.status,
                        "headers": dict(resp.headers),
                        "body": resp.read().decode("utf-8", "ignore"),
                    }
            except urllib.error.HTTPError as error:
                return {
                    "statusCode": error.code,
                    "headers": dict(error.headers or {}),
                    "body": str(error.reason or ""),
                }
            except Exception as error:
                return {"statusCode": 0, "headers": {}, "body": str(error)}

    OmniBox = _FallbackOmniBox()

    def run(handlers):
        print(f"[fallback] spider_runner 缺失，已跳过本地启动: {sorted(handlers)}")


# ==================== 配置区域 ====================
HOST = os.environ.get("DMHY_HOST", "https://dmhyy.com").rstrip("/")
WEB_SIGN = os.environ.get("DMHY_WEB_SIGN", "")
UA = os.environ.get(
    "DMHY_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
)
# 大马猴真实分类 ID 来自网页 /type/xx 与 XHR 返回：23 电影，22 剧集，24 动漫，25 综艺
CLASS_LIST = [
    {"type_id": "23", "type_name": "电影"},
    {"type_id": "22", "type_name": "剧集"},
    {"type_id": "24", "type_name": "动漫"},
    {"type_id": "25", "type_name": "综艺"},
]
CLASS_IDS = {item["type_id"] for item in CLASS_LIST}
# 兼容旧配置或壳缓存仍传入 1/2/3/4 的情况
TID_MAP = {"1": "23", "2": "22", "3": "24", "4": "25"}
DEFAULT_TYPE_ID = "23"
PAGE_LIMIT = 24
EXTERNAL_VIDEO_HOSTS = r"(v\.qq\.com|youku\.com|iqiyi\.com|mgtv\.com|bilibili\.com)"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return "".join(self._text)


async def log(level, message):
    try:
        await OmniBox.log(level, f"[大马猴影视] {message}")
    except Exception:
        pass


def build_headers(referer=""):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer or (HOST + "/"),
        "x-platform": "web",
        "x-requested-with": "XMLHttpRequest",
    }
    # 大马猴当前播放页 XHR 不需要 web-sign；若环境变量显式提供则带上
    if WEB_SIGN:
        headers["web-sign"] = WEB_SIGN
    return headers


async def api_get(path, params=None, referer=""):
    """
    统一请求站点 JSON 接口；失败记录原因并返回 {}，由调用方决定兜底行为。
    """
    params = params or {}
    query = urlencode(params, doseq=True)
    url = HOST + path + (("?" + query) if query else "")
    try:
        response = await OmniBox.request(
            url,
            {"method": "GET", "headers": build_headers(referer), "timeout": 12000},
        )
        status = int(response.get("statusCode") or 0)
        body = response.get("body", "")
        text = (
            body.decode("utf-8", "ignore")
            if isinstance(body, (bytes, bytearray))
            else str(body or "")
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"HTTP {status}")
        return json.loads(text) if text else {}
    except Exception as error:
        await log("error", f"[api] 失败 url={url} 原因={error}")
        return {}


def to_int(value, default=0):
    try:
        return int(float(value)) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return default


def clean_text(value):
    text = html_unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def html2text(value):
    try:
        parser = _HTMLTextExtractor()
        parser.feed(str(value or ""))
        return clean_text(parser.get_text())
    except Exception:
        return clean_text(value)


def as_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "list", "items", "records", "rows", "vod_list"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = as_list(value)
                if nested:
                    return nested
    return []


def is_direct_media(url):
    # 选集字符串中经常是 .m3u8#下一集，不能只判断 ? 或结尾
    return bool(re.search(r"\.(m3u8|mp4|flv|mkv|avi)(\?|#|$|\s)", str(url or ""), re.I))


def vod_item(item):
    if not isinstance(item, dict):
        return None
    vid = item.get("vod_id") or item.get("id") or item.get("vodId")
    name = item.get("vod_name") or item.get("name") or item.get("title")
    if not vid or not name:
        return None
    area = item.get("vod_area", "")
    cls = item.get("vod_class", "")
    if isinstance(area, list):
        area = ",".join([str(x) for x in area if x])
    if isinstance(cls, list):
        cls = ",".join([str(x) for x in cls if x])
    return {
        "vod_id": str(vid),
        "vod_name": clean_text(name),
        "vod_pic": str(item.get("vod_pic") or item.get("pic") or item.get("cover") or ""),
        "vod_remarks": str(
            item.get("vod_remarks")
            or item.get("remarks")
            or item.get("vod_douban_score")
            or item.get("vod_year")
            or ""
        ),
        "vod_year": str(item.get("vod_year") or ""),
        "type_name": clean_text(item.get("type_name") or cls or ""),
        "vod_area": clean_text(area),
    }


def vod_list(data):
    out = []
    seen = set()
    for item in as_list(data):
        video = vod_item(item)
        if not video or video["vod_id"] in seen:
            continue
        seen.add(video["vod_id"])
        out.append(video)
    return out


def category_match(item, real_tid):
    """
    接口即使传 type_id=22 也会混入电影/动漫/综艺，必须按真实 type_id/type_name 再过滤一次。
    """
    if not isinstance(item, dict):
        return False
    real_tid = str(real_tid)
    item_tid = str(item.get("type_id") or item.get("typeId") or item.get("tid") or "")
    if item_tid == real_tid:
        return True
    name = str(item.get("type_name") or "")
    class_value = item.get("vod_class") or []
    if isinstance(class_value, list):
        cls = ",".join([str(x) for x in class_value if x])
    else:
        cls = str(class_value or "")
    text = name + "," + cls
    if real_tid == "23":
        return (
            "电影" in text or "动作片" in text or "剧情片" in text or "喜剧片" in text
        ) and "电视剧" not in text
    if real_tid == "22":
        return any(
            key in text
            for key in ("剧集", "电视剧", "国产剧", "连续剧", "韩剧", "陆剧", "欧美剧", "日剧")
        )
    if real_tid == "24":
        return "动漫" in text or "动画" in text or "国产动漫" in text or "日韩动漫" in text
    if real_tid == "25":
        return "综艺" in text or "真人秀" in text
    return True


def filter_items_by_category(data, real_tid):
    return [x for x in as_list(data) if category_match(x, real_tid)]


def parse_episodes(play_url):
    """
    采集站线路串：第1集$url1#第2集$url2 → [{name, playId}]
    """
    episodes = []
    for index, segment in enumerate(str(play_url or "").split("#")):
        segment = segment.strip()
        if not segment:
            continue
        if "$" in segment:
            name, play_id = segment.split("$", 1)
        else:
            name, play_id = f"第{index + 1}集", segment
        name = clean_text(name) or f"第{index + 1}集"
        play_id = play_id.strip()
        if play_id:
            episodes.append({"name": name, "playId": play_id})
    return episodes


def build_play_result(url, flag, parse, header=None):
    headers = header or {"User-Agent": "Mozilla/5.0", "Referer": HOST + "/"}
    return {
        "parse": int(parse),
        "url": url,
        "urls": [{"name": flag or "播放", "url": url}] if url else [],
        "flag": flag,
        "header": headers,
        "headers": headers,
    }


def line_rank(src):
    name = str(
        src.get("site_name") or src.get("external_display_name") or src.get("vod_play_from") or ""
    ).lower()
    from_code = str(src.get("vod_play_from") or src.get("external_play_from") or "").lower()
    url = str(src.get("vod_play_url") or "")
    # 只要线路里已经是 m3u8/mp4，就按直链线路优先；decode_status 不再作为过滤条件
    if is_direct_media(url):
        if "暴风" in name or "bfzy" in from_code:
            return 1
        if "爱坤" in name or "ikm3u8" in from_code:
            return 2
        if "极速" in name or "jsm3u8" in from_code:
            return 3
        if "如意" in name or "rym3u8" in from_code:
            return 4
        if "量子" in name or "lzm3u8" in from_code:
            return 5
        return 10
    if to_int(src.get("decode_status") or 0) == 0:
        return 50
    return 99


async def aggregate_sources(vid):
    # 播放页会请求这个聚合接口，里面有很多站外直链 m3u8，必须带 /play/<vid> Referer
    for path in (
        "/api.php/web/internal/search_aggregate",
        "/api.php/web/search_aggregate",
    ):
        data = await api_get(path, {"vod_id": str(vid)}, HOST + "/play/" + str(vid))
        items = as_list(data)
        if items:
            return items
    return []


def build_sources(vid, detail, aggregate_items):
    """
    返回 [(线路名, 线路播放串)]，优先聚合接口直链线路。
    """
    sources = []
    seen = set()

    def add_source(name, play_url):
        name = clean_text(name or "")
        play_url = str(play_url or "").strip()
        if not name or not play_url:
            return
        key = name + "|" + play_url[:80]
        if key in seen:
            return
        seen.add(key)
        sources.append((name, play_url))

    # 1. 优先用真实聚合接口，它返回的是可直接播放的 m3u8 线路
    if aggregate_items:
        for src in sorted(aggregate_items, key=line_rank):
            play_url = str(src.get("vod_play_url") or "").strip()
            if not play_url or not is_direct_media(play_url):
                continue
            line_name = (
                src.get("site_name")
                or src.get("external_display_name")
                or src.get("external_play_from")
                or src.get("vod_play_from")
                or "线路"
            )
            add_source(line_name, play_url)
            if len(sources) >= 4:
                break

    # 2. 兜底：从 get_detail 里只提取含 m3u8/mp4 的线路，过滤 JD/QQ 这类需二次解析的超长线路
    froms = str(detail.get("vod_play_from") or "").split("$$$")
    urls = str(detail.get("vod_play_url") or "").split("$$$")
    if froms and urls and froms[0] and urls[0] and len(sources) < 2:
        for index, name in enumerate(froms):
            play_url = urls[index] if index < len(urls) else ""
            if not name or not play_url or not is_direct_media(play_url):
                continue
            add_source(name, play_url)
            if len(sources) >= 4:
                break

    # 3. 最后兜底：完全没有直链时，再少量加入解析线路
    if not sources and froms[0] and urls[0]:
        for index, name in enumerate(froms[:3]):
            play_url = urls[index] if index < len(urls) else ""
            add_source(name, play_url)

    return sources


async def home(params, context):
    try:
        params = params or {}
        context = context or {}
        await log("info", f"[home] from={context.get('from', 'web')} params={params}")
        # 用电影热门做首页推荐
        data = await api_get(
            "/api.php/web/filter/vod",
            {"type_id": DEFAULT_TYPE_ID, "page": "1", "sort": "hits"},
            HOST + "/type/" + DEFAULT_TYPE_ID,
        )
        videos = vod_list(data)
        await log("info", f"[home] class={len(CLASS_LIST)} list={len(videos)}")
        return {"class": list(CLASS_LIST), "list": videos, "filters": {}}
    except Exception as error:
        await log("error", f"[home] 失败: {error}")
        return {"class": list(CLASS_LIST), "list": [], "filters": {}}


async def category(params, context):
    try:
        params = params or {}
        filters = params.get("filters") or {}
        real_tid = TID_MAP.get(
            str(params.get("categoryId") or DEFAULT_TYPE_ID),
            str(params.get("categoryId") or DEFAULT_TYPE_ID),
        )
        page = max(1, to_int(params.get("page"), 1))
        sort = str(
            (filters.get("sort") if isinstance(filters, dict) else None)
            or (filters.get("by") if isinstance(filters, dict) else None)
            or "hits"
        )
        referer = HOST + "/type/" + real_tid

        await log("info", f"[category] categoryId={real_tid}, page={page}, sort={sort}")
        data = await api_get(
            "/api.php/web/filter/vod",
            {"type_id": real_tid, "page": str(page), "sort": sort},
            referer,
        )
        filtered = filter_items_by_category(data, real_tid)

        # 当前页过滤后太少时，补抓后面 2 页同分类资源，避免分类页空白
        if len(filtered) < 8:
            seen_ids = set(
                str(x.get("vod_id") or x.get("id") or "") for x in filtered if isinstance(x, dict)
            )
            for extra_page in range(page + 1, page + 3):
                extra = await api_get(
                    "/api.php/web/filter/vod",
                    {"type_id": real_tid, "page": str(extra_page), "sort": sort},
                    referer,
                )
                for item in filter_items_by_category(extra, real_tid):
                    vid = str(item.get("vod_id") or item.get("id") or "")
                    if vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        filtered.append(item)
                if len(filtered) >= PAGE_LIMIT:
                    break

        videos = vod_list(filtered)
        pagecount = page + 1 if videos else page
        total = len(videos)
        limit = PAGE_LIMIT
        if isinstance(data, dict):
            pagecount = to_int(data.get("pageCount") or data.get("pagecount"), 0) or pagecount
            total = to_int(data.get("total"), 0) or total
            limit = to_int(data.get("limit"), 0) or limit

        await log(
            "info",
            f"[category] count={len(videos)} pagecount={pagecount} total={total}",
        )
        return {"page": page, "pagecount": pagecount, "limit": limit, "total": total, "list": videos}
    except Exception as error:
        await log("error", f"[category] 失败: {error}")
        return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}


async def search(params, context):
    try:
        params = params or {}
        keyword = clean_text(params.get("keyword") or params.get("wd") or params.get("key"))
        page = max(1, to_int(params.get("page"), 1))
        if not keyword:
            return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}

        await log("info", f"[search] keyword={keyword}, page={page}")
        # 真实网页搜索接口（其余候选接口均 404/无效）
        data = await api_get(
            "/api.php/web/search/index",
            {"wd": keyword, "page": str(page)},
            HOST + "/search?keyword=" + quote(keyword),
        )
        videos = vod_list(data)
        pagecount = page + 1 if videos else page
        total = len(videos)
        if isinstance(data, dict):
            pagecount = to_int(data.get("pageCount") or data.get("pagecount"), 0) or pagecount
            total = to_int(data.get("total"), 0) or total
        await log("info", f"[search] count={len(videos)} pagecount={pagecount}")
        return {"page": page, "pagecount": pagecount, "limit": PAGE_LIMIT, "total": total, "list": videos}
    except Exception as error:
        await log("error", f"[search] 失败: {error}")
        return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}


async def detail(params, context):
    try:
        params = params or {}
        video_id = str(
            params.get("videoId") or params.get("vod_id") or params.get("id") or ""
        ).strip()
        if not video_id:
            return {"list": []}

        await log("info", f"[detail] videoId={video_id}")
        raw = await api_get(
            "/api.php/web/vod/get_detail",
            {"vod_id": video_id},
            HOST + "/play/" + video_id,
        )
        items = as_list(raw)
        detail_item = items[0] if items else {}

        aggregate_items = []
        if not detail_item:
            aggregate_items = await aggregate_sources(video_id)
            if not aggregate_items:
                await log("warn", f"[detail] 详情与聚合线路均为空 id={video_id}")
                return {"list": []}
            detail_item = aggregate_items[0]
        else:
            aggregate_items = await aggregate_sources(video_id)

        area = detail_item.get("vod_area", "")
        cls = detail_item.get("vod_class", "")
        if isinstance(area, list):
            area = ",".join([str(x) for x in area if x])
        if isinstance(cls, list):
            cls = ",".join([str(x) for x in cls if x])

        pairs = build_sources(video_id, detail_item, aggregate_items)
        play_sources = []
        raw_play_urls = []
        for name, play_url in pairs:
            episodes = parse_episodes(play_url)
            if not episodes:
                continue
            play_sources.append({"name": name, "episodes": episodes})
            raw_play_urls.append(play_url)

        vod = {
            "vod_id": video_id,
            "vod_name": clean_text(detail_item.get("vod_name") or ""),
            "vod_pic": str(detail_item.get("vod_pic") or ""),
            "vod_remarks": str(detail_item.get("vod_remarks") or ""),
            "type_name": clean_text(detail_item.get("type_name") or cls or ""),
            "vod_year": str(detail_item.get("vod_year") or ""),
            "vod_area": clean_text(area),
            "vod_actor": clean_text(detail_item.get("vod_actor") or ""),
            "vod_director": clean_text(detail_item.get("vod_director") or ""),
            "vod_content": html2text(detail_item.get("vod_content") or ""),
            "vod_play_sources": play_sources,
            # 兼容旧版 UI 的 legacy 字段
            "vod_play_from": "$$$".join([source["name"] for source in play_sources]),
            "vod_play_url": "$$$".join(raw_play_urls),
        }
        await log(
            "info",
            f"[detail] id={video_id} name={vod['vod_name']} "
            f"sources={len(play_sources)} episodes={sum(len(s['episodes']) for s in play_sources)}",
        )
        return {"list": [vod]}
    except Exception as error:
        await log("error", f"[detail] 失败: {error}")
        return {"list": []}


async def play(params, context):
    try:
        params = params or {}
        context = context or {}
        play_id = clean_text(params.get("playId") or params.get("id") or params.get("url"))
        flag = clean_text(params.get("flag")) or "线路1"
        if not play_id:
            return build_play_result("", flag, 0)

        await log(
            "info",
            f"[play] playId={play_id[:120]} flag={flag} from={context.get('from', 'web')}",
        )

        # 直链直接播放
        if play_id.startswith("http") and is_direct_media(play_id):
            return build_play_result(play_id, flag, 0)

        # 官方站外编码线路尝试用 decode 接口解析
        for key in ("url", "play_url", "vod_url"):
            data = await api_get(
                "/api.php/web/decode/url", {key: play_id}, HOST + "/play"
            )
            payload = data.get("data") if isinstance(data, dict) else None
            final_url = ""
            headers = {}
            if isinstance(payload, str):
                final_url = payload
            elif isinstance(payload, dict):
                final_url = (
                    payload.get("url")
                    or payload.get("play_url")
                    or payload.get("playUrl")
                    or payload.get("video")
                    or ""
                )
                headers = payload.get("header") or payload.get("headers") or {}
            elif isinstance(data, dict):
                final_url = data.get("url") or data.get("play_url") or ""
                headers = data.get("header") or data.get("headers") or {}

            if final_url:
                parse_mode = 0 if is_direct_media(final_url) else 1
                await log("info", f"[play] decode 命中 key={key} parse={parse_mode}")
                return build_play_result(final_url, flag, parse_mode, headers or None)

        # 腾讯/优酷/爱奇艺等外部网页地址与其它未知地址交给客户端嗅探（parse=1 仅 ok影视 app 生效）
        if re.search(EXTERNAL_VIDEO_HOSTS, play_id, re.I):
            await log("info", "[play] 外部站点地址，回退嗅探")
        else:
            await log("warn", "[play] 未解出直链，回退嗅探")
        return build_play_result(play_id, flag, 1)
    except Exception as error:
        await log("error", f"[play] 失败: {error}")
        return build_play_result("", clean_text((params or {}).get("flag")) or "线路1", 0)


if __name__ == "__main__":
    run({"home": home, "category": category, "detail": detail, "search": search, "play": play})
