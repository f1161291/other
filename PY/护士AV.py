# -*- coding: utf-8 -*-
# @name 护士AV
# @description 影视站：https://vip.hushiav9.cc ，采集站结构，支持首页分类、分类列表、搜索、详情与 m3u8 直链播放
# @version 1.0.0
# @downloadURL https://gh-proxy.org/https://github.com/f1161291/other/edit/main/PY/护士AV.py

# =============================================================================
# 护士AV (https://vip.hushiav9.cc)
#
# 功能特性：
# - 首页分类 / 分类分页 / 搜索 / 详情 / 播放 全链路支持
# - 播放优先直取 player_aaaa.url，主清单自动解析为媒体清单
# - 详情同时返回 vod_play_sources 与 vod_play_from / vod_play_url（兼容旧版 UI）
#
# 环境变量：
# - HUSHIAV_HOST：站点地址（默认 https://vip.hushiav9.cc）
# - HUSHIAV_UA：请求 UA（可选）
# - HUSHIAV_PREFIX：站点路径前缀（默认 /a）
# =============================================================================

import json
import os
import re
from html import unescape as html_unescape
from urllib.parse import quote, urljoin

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
HOST = os.environ.get("HUSHIAV_HOST", "https://vip.hushiav9.cc").rstrip("/")
PREFIX = os.environ.get("HUSHIAV_PREFIX", "/a")
UA = os.environ.get(
    "HUSHIAV_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
HEADERS = {
    "User-Agent": UA,
    "Referer": HOST + PREFIX + "/",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "identity",
}
CLASS_LIST = [
    {"type_id": "387", "type_name": "国产自拍"},
    {"type_id": "254", "type_name": "国产自拍2"},
    {"type_id": "255", "type_name": "熟女人妻"},
    {"type_id": "388", "type_name": "日本无码"},
    {"type_id": "365", "type_name": "高清无码"},
    {"type_id": "366", "type_name": "中文字幕"},
    {"type_id": "389", "type_name": "主播系列"},
    {"type_id": "363", "type_name": "主播网红"},
    {"type_id": "364", "type_name": "黑料网曝"},
    {"type_id": "258", "type_name": "美乳巨乳"},
    {"type_id": "391", "type_name": "欧美"},
    {"type_id": "264", "type_name": "欧美无码"},
    {"type_id": "369", "type_name": "高清有码"},
    {"type_id": "266", "type_name": "AV解说"},
    {"type_id": "128", "type_name": "国产主播"},
    {"type_id": "304", "type_name": "精品推荐"},
    {"type_id": "307", "type_name": "日本无码2"},
    {"type_id": "310", "type_name": "性感人妻"},
]
CLASS_IDS = {item["type_id"] for item in CLASS_LIST}
DEFAULT_CATEGORY_ID = "387"
PAGE_LIMIT = 24
BLOCKED_KEYWORDS = ("萝莉", "幼女")


async def log(level, message):
    try:
        await OmniBox.log(level, f"[护士AV] {message}")
    except Exception:
        pass


async def fetch(path, retry=2):
    """
    统一请求站点页面：拼 URL、判状态码、返回文本；失败抛错由 handler 记录原因。
    """
    url = path if str(path).startswith("http") else HOST + PREFIX + str(path)
    last_error = ""
    for attempt in range(retry + 1):
        try:
            response = await OmniBox.request(
                url,
                {"method": "GET", "headers": dict(HEADERS), "timeout": 15000},
            )
            status = int(response.get("statusCode") or 0)
            body = response.get("body", "")
            text = (
                body.decode("utf-8", "ignore")
                if isinstance(body, (bytes, bytearray))
                else str(body or "")
            )
            if 200 <= status < 300 and text and "404 Not Found" not in text[:200]:
                return text
            last_error = f"HTTP {status}"
        except Exception as error:
            last_error = str(error)
        if attempt < retry:
            await log("warn", f"[请求] 第 {attempt + 1} 次失败 url={url} 原因={last_error}")
    raise RuntimeError(f"请求失败 {url}: {last_error}")


def to_int(value, default=0):
    try:
        return int(float(value)) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return default


def clean_text(value):
    return html_unescape(str(value or "")).strip()


def is_direct_media(url):
    return bool(re.search(r"\.(?:m3u8|mp4|mkv|flv|mpd)(?:[?#]|$)", url or "", re.I))


def extract_page_count(html, pattern, pg, count):
    """
    从分页链接推断总页数；没有链接时按“满页”假设还有下一页。
    """
    pagecount = pg
    pages = re.findall(pattern, html or "")
    if pages:
        pagecount = max(to_int(x, 0) for x in pages)
    if pagecount <= pg and count >= PAGE_LIMIT:
        pagecount = pg + 1
    return pagecount


def parse_list(html):
    videos = []
    for match in re.finditer(
        r'href="%s/index\.php/vod/detail/id/(\d+)[^"]*"[\s\S]{0,500}?data-original="([^"]*)"[\s\S]{0,200}?alt="([^"]*)"'
        % re.escape(PREFIX),
        html or "",
    ):
        vid, pic, name = match.group(1), match.group(2), clean_text(match.group(3))
        if len(name) < 2 or any(keyword in name for keyword in BLOCKED_KEYWORDS):
            continue
        videos.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": ""})
    if not videos:
        for match in re.finditer(
            r'href="%s/index\.php/vod/detail/id/(\d+)[^"]*"' % re.escape(PREFIX),
            html or "",
        ):
            vid = match.group(1)
            chunk = html[match.start():match.start() + 600]
            pic_match = re.search(r'data-original="([^"]+)"', chunk)
            name = ""
            name_match = re.search(r'class="vod-name"[^>]*>([\s\S]*?)</div>', chunk)
            if name_match:
                name = clean_text(re.sub(r"<[^>]+>", "", name_match.group(1)))
            if not name:
                alt_match = re.search(r'alt="([^"]+)"', chunk)
                if alt_match:
                    name = clean_text(alt_match.group(1))
            if len(name) < 2 or any(keyword in name for keyword in BLOCKED_KEYWORDS):
                continue
            videos.append(
                {
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": pic_match.group(1) if pic_match else "",
                    "vod_remarks": "",
                }
            )
    seen = set()
    unique = []
    for video in videos:
        if video["vod_id"] in seen:
            continue
        seen.add(video["vod_id"])
        unique.append(video)
    return unique


def build_list_page(videos, pg, pagecount):
    return {
        "page": pg,
        "pagecount": pagecount,
        "limit": PAGE_LIMIT,
        "total": pagecount * PAGE_LIMIT,
        "list": videos,
    }


def build_legacy_play_fields(sources):
    from_names = []
    url_groups = []
    for source in sources:
        from_names.append(clean_text(source.get("name")) or "线路1")
        url_groups.append(
            "#".join(
                f"{clean_text(episode.get('name')) or '正片'}${clean_text(episode.get('playId'))}"
                for episode in source.get("episodes") or []
                if clean_text(episode.get("playId"))
            )
        )
    return "|".join(from_names), "|".join(url_groups)


def build_play_result(url, flag, parse, header=None):
    headers = header or {
        "User-Agent": UA,
        "Referer": HOST + "/",
    }
    return {
        "parse": int(parse),
        "url": url,
        "urls": [{"name": flag or "播放", "url": url}] if url else [],
        "flag": flag,
        "header": headers,
        "headers": headers,
    }


def extract_player_url(html):
    match = re.search(r"player_aaaa\s*=\s*(\{.+?\})\s*</script>", html or "", re.S)
    if not match:
        return ""
    try:
        return str(json.loads(match.group(1)).get("url") or "").strip()
    except Exception:
        url_match = re.search(r'"url"\s*:\s*"([^"]+)"', match.group(1))
        if url_match:
            return url_match.group(1).replace("\\/", "/")
    return ""


async def resolve_m3u8(url):
    """
    主清单 → 媒体清单：返回第一层可播的子清单地址，避免客户端解析多级 master。
    """
    if not url or ".m3u8" not in url:
        return url
    body = await fetch(url)
    if not body:
        return url
    if "#EXTINF" in body and "#EXT-X-STREAM-INF" not in body:
        return url
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and ".m3u8" in line:
            return line if line.startswith("http") else urljoin(url, line)
    return url


async def home(params, context):
    try:
        params = params or {}
        context = context or {}
        await log(
            "info",
            f"[home] from={context.get('from', 'web')} params={params}",
        )
        videos = []
        try:
            html = await fetch(f"/index.php/vod/type/id/{DEFAULT_CATEGORY_ID}.html")
            videos = parse_list(html)
        except Exception as error:
            await log("warn", f"[home] 推荐列表获取失败: {error}")
        await log("info", f"[home] class={len(CLASS_LIST)} list={len(videos)}")
        return {"class": list(CLASS_LIST), "list": videos, "filters": {}}
    except Exception as error:
        await log("error", f"[home] 失败: {error}")
        return {"class": list(CLASS_LIST), "list": [], "filters": {}}


async def category(params, context):
    try:
        params = params or {}
        category_id = str(params.get("categoryId") or DEFAULT_CATEGORY_ID)
        page = max(1, to_int(params.get("page"), 1))
        if category_id not in CLASS_IDS:
            await log("warn", f"[category] 未知分类 {category_id}，回退默认分类")

        if page == 1:
            path = f"/index.php/vod/type/id/{category_id}.html"
        else:
            path = f"/index.php/vod/type/id/{category_id}/page/{page}.html"

        await log("info", f"[category] categoryId={category_id}, page={page}")
        html = await fetch(path)
        videos = parse_list(html)
        pagecount = extract_page_count(
            html, r"type/id/%s/page/(\d+)" % re.escape(category_id), page, len(videos)
        )
        await log(
            "info",
            f"[category] count={len(videos)} pagecount={pagecount}",
        )
        return build_list_page(videos, page, pagecount)
    except Exception as error:
        await log("error", f"[category] 失败: {error}")
        return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}


async def detail(params, context):
    try:
        params = params or {}
        video_id = str(
            params.get("videoId") or params.get("vod_id") or params.get("id") or ""
        ).strip()
        video_id = re.sub(r"\D", "", video_id)
        if not video_id:
            return {"list": []}

        await log("info", f"[detail] videoId={video_id}")
        html = await fetch(f"/index.php/vod/detail/id/{video_id}.html")

        name = ""
        name_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
        if name_match:
            name = clean_text(name_match.group(1))
        if not name:
            title_match = re.search(r"<title>([^<]+)</title>", html)
            if title_match:
                name = clean_text(title_match.group(1))
                name = re.sub(r"^《|》.*$", "", name)
                name = name.split("在线")[0].split(" - ")[0].strip()

        pic = ""
        pic_match = re.search(r'data-original="(https?://[^"]+)"', html)
        if pic_match:
            pic = pic_match.group(1)

        sources = [
            {
                "name": "线路1",
                "episodes": [{"name": "正片", "playId": video_id}],
            }
        ]
        play_from, play_url = build_legacy_play_fields(sources)

        item = {
            "vod_id": video_id,
            "vod_name": name or f"视频{video_id}",
            "vod_pic": pic,
            "vod_content": name,
            "vod_remarks": "",
            "vod_play_sources": sources,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        await log(
            "info",
            f"[detail] id={video_id} name={item['vod_name']} "
            f"sources={len(sources)} episodes={len(sources[0]['episodes'])}",
        )
        return {"list": [item]}
    except Exception as error:
        await log("error", f"[detail] 失败: {error}")
        return {"list": []}


async def search(params, context):
    try:
        params = params or {}
        keyword = clean_text(
            params.get("keyword") or params.get("wd") or params.get("key")
        )
        page = max(1, to_int(params.get("page"), 1))
        if not keyword:
            return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}

        encoded = quote(keyword, safe="")
        if page == 1:
            path = f"/index.php/vod/search.html?wd={encoded}"
        else:
            path = f"/index.php/vod/search/page/{page}/wd/{encoded}.html"

        await log("info", f"[search] keyword={keyword}, page={page}")
        html = await fetch(path)
        videos = parse_list(html or "")
        pagecount = extract_page_count(
            html, r"search/page/(\d+)/wd/", page, len(videos)
        )
        await log("info", f"[search] count={len(videos)} pagecount={pagecount}")
        return build_list_page(videos, page, pagecount)
    except Exception as error:
        await log("error", f"[search] 失败: {error}")
        return {"page": 1, "pagecount": 0, "limit": PAGE_LIMIT, "total": 0, "list": []}


async def play(params, context):
    try:
        params = params or {}
        context = context or {}
        play_id = clean_text(
            params.get("playId") or params.get("id") or params.get("url")
        )
        flag = clean_text(params.get("flag")) or "线路1"
        if not play_id:
            return build_play_result("", flag, 0)

        if str(play_id).startswith("http"):
            url = await resolve_m3u8(play_id)
            parse_mode = 0 if is_direct_media(url) else 1
            await log("info", f"[play] 直链 from={context.get('from', 'web')} parse={parse_mode}")
            return build_play_result(url, flag, parse_mode)

        play_page = f"/index.php/vod/play/id/{play_id}/sid/1/nid/1.html"
        await log("info", f"[play] playId={play_id}, flag={flag}")
        html = await fetch(play_page)
        stream_url = await resolve_m3u8(extract_player_url(html))
        if not stream_url:
            # 未取到媒体直链时回退嗅探（parse=1 仅 ok影视 app 生效）
            await log("warn", f"[play] 未提取直链，回退嗅探: {play_page}")
            return build_play_result(HOST + PREFIX + play_page, flag, 1)

        parse_mode = 0 if is_direct_media(stream_url) else 1
        await log("info", f"[play] parse={parse_mode} url={stream_url[:80]}")
        return build_play_result(stream_url, flag, parse_mode)
    except Exception as error:
        await log("error", f"[play] 失败: {error}")
        return build_play_result("", clean_text((params or {}).get("flag")) or "线路1", 0)


if __name__ == "__main__":
    run({"home": home, "category": category, "detail": detail, "search": search, "play": play})
