# -*- coding: utf-8 -*-
# @name 黄果短剧
# @version 1.0.0
# @downloadURL https://raw.githubusercontent.com/your-repo/omnibox-spiders/main/Huangguo.py
# @dependencies pycryptodome
# @description 黄果短剧 huangguoai.com OmniBox 源 (spider_runner 五方法形态)
#   - 分类: recommend/ai-duanju/ai-manju/ai-huanlian/ai-mogai/ranks/chigua/topics
#   - 排序筛选: latest/hot/original/random; 榜单 hot/recommend/potential; 吃瓜 all/remen/yuanchuang; 话题 6 个
#   - 列表 API: /api/videos/category/{id}?page=&size=&sort= ; 榜单 /api/ranks/{type}
#   - 详情: /video/{vid}/ HTML, 内嵌 epPlaySrcs JSON (集数->m3u8)
#   - 播放: m3u8 直链 (yd-hls.hrppxr.cn, 带 auth_key 时效签名, parse=0)
#   - 封面: pic.zdmhyg.cn 是 AES-CBC 密文 (key/iv 与 91crdj 同源),
#           脚本内下载解密转 base64 data URI (OmniBox 无 localProxy)
import asyncio
import base64
import json
import os
import re
import ssl
import sys
import time
from urllib.parse import quote, urljoin, urlparse

# ===== 配置 =====
HOST = "https://huangguoai.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# 封面 AES-CBC 密钥 (与 91crdj 同源, crypto-worker.js 明文常量)
IMG_KEY_RAW = "102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48"
IMG_IV_RAW = "57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49"
ENCRYPTED_HOSTS = {"pic.zdmhyg.cn", "pic.eanfog.cn"}
PAGE_SIZE = 20

# 频道: (type_id, 名称)
CATEGORIES = [
    ("recommend", "⭐精选推荐"),
    ("ai-duanju", "🎬 AI成人短剧"),
    ("ai-manju", "🎬 AI成人漫剧"),
    ("ai-huanlian", "🎬 AI换脸"),
    ("ai-mogai", "🎬 AI魔改"),
    ("ranks", "📊排行榜"),
    ("chigua", "🍉黄果吃瓜"),
    ("topics", "📰话题精选"),
]

# ===== spider_runner SDK (带本地 fallback) =====
try:
    from spider_runner import OmniBox, run
except Exception:
    class _OmniBox(object):
        @staticmethod
        def log(level, message):
            print("[%s] %s" % (level, message))
        @staticmethod
        async def request(url, options=None):
            import urllib.request
            opts = options or {}
            headers = {"User-Agent": UA, "Accept": "text/html,application/json,*/*"}
            headers.update(opts.get("headers") or {})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=headers, method=opts.get("method", "GET"))
            if opts.get("body"):
                body = opts["body"]
                if isinstance(body, (dict, list)):
                    body = json.dumps(body)
                req.data = body.encode("utf-8") if isinstance(body, str) else body
            try:
                resp = urllib.request.urlopen(req, timeout=25, context=ctx)
                return {"statusCode": resp.status, "headers": dict(resp.headers),
                        "body": resp.read().decode("utf-8", errors="replace")}
            except urllib.error.HTTPError as e:
                return {"statusCode": e.code, "headers": dict(e.headers),
                        "body": e.read().decode("utf-8", errors="replace")}
            except Exception as e:
                return {"statusCode": -1, "headers": {}, "body": str(e)}
        @staticmethod
        def get_env(name):
            return os.environ.get(name, "")
    OmniBox = _OmniBox
    def run(handlers):
        pass

# ===== 运行时状态 =====
_page_cache = {}

def _headers(referer=None):
    h = {
        "User-Agent": UA,
        "Accept": "text/html,application/json,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": HOST + "/",
    }
    if referer:
        h["Referer"] = referer
    return h

async def _html(url, referer=None):
    """文本请求 (带简单缓存)"""
    if url in _page_cache:
        return _page_cache[url]
    try:
        res = await OmniBox.request(url, {"method": "GET", "headers": _headers(referer)})
        if res.get("statusCode") in (200, 301, 302):
            body = res.get("body", "") or ""
            if res.get("statusCode") == 200 and body:
                if len(_page_cache) > 40:
                    _page_cache.clear()
                _page_cache[url] = body
            return body
    except Exception as e:
        OmniBox.log("warn", "[黄果][html] 请求失败 %s: %s" % (url[:80], e))
    return ""

async def _get_json(path, params=None):
    """GET JSON API"""
    from urllib.parse import urlencode
    url = HOST + path
    if params:
        url += "?" + urlencode(params)
    try:
        res = await OmniBox.request(url, {"method": "GET", "headers": _headers()})
        if res.get("statusCode") == 200:
            return json.loads(res.get("body", "{}"))
    except Exception as e:
        OmniBox.log("warn", "[黄果][json] 失败 %s: %s" % (path, e))
    return {}

def _fetch_binary(url, timeout=20):
    """二进制请求 (封面密文) — urllib 直连"""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": HOST + "/",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()

# ===== 封面解密 =====
def _img_key_iv():
    def conv(raw):
        return "".join(chr(int(x)) for x in raw.split("_")).encode("utf-8")
    return conv(IMG_KEY_RAW), conv(IMG_IV_RAW)

def _decrypt_image(body):
    if not body:
        return None
    key, iv = _img_key_iv()
    data = body[:len(body) - len(body) % 16]
    if not data:
        return None
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    except Exception:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return c.update(data) + c.finalize()
    except Exception:
        return None

def _image_datauri(body):
    out = _decrypt_image(body)
    if not out:
        return ""
    mime = "image/jpeg"
    if out[:8] == b'\x89PNG\r\n\x1a\n':
        mime = "image/png"
    elif out[:3] == b'GIF':
        mime = "image/gif"
    elif out[:4] == b'RIFF' and out[8:12] == b'WEBP':
        mime = "image/webp"
    elif out[:2] != b'\xff\xd8':
        return ""
    return "data:%s;base64,%s" % (mime, base64.b64encode(out).decode("ascii"))

def _is_encrypted_pic(url):
    try:
        return urlparse(url).hostname in ENCRYPTED_HOSTS
    except Exception:
        return False

async def _resolve_pic(raw_url):
    url = str(raw_url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = urljoin(HOST + "/", url.lstrip("/"))
    url = url.replace("\\u0026", "&").replace("&amp;", "&")
    if not _is_encrypted_pic(url):
        return url
    try:
        loop = asyncio.get_event_loop()
        body = await loop.run_in_executor(None, _fetch_binary, url)
        if not body:
            return url
        return _image_datauri(body) or url
    except Exception as e:
        OmniBox.log("warn", "[黄果][pic] 解密失败 %s: %s" % (url[:60], e))
        return url

async def _enrich_pics(videos):
    if not videos:
        return
    tasks = [_resolve_pic(v.get("vod_pic", "")) for v in videos]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if not isinstance(r, Exception) and r:
            videos[i]["vod_pic"] = r

# ===== 工具 =====
def _remarks(item):
    if not isinstance(item, dict):
        return ""
    ep = item.get("episode_count") or item.get("total_episodes") or 0
    try:
        ep = int(ep)
    except Exception:
        ep = 0
    if item.get("is_finished") and ep:
        return "全%d集" % ep
    if ep:
        return "更新至%d集" % ep
    return ""

def _norm_pic(pic):
    pic = str(pic or "").replace("\\u0026", "&").replace("&amp;", "&").strip()
    if pic.startswith("//"):
        pic = "https:" + pic
    elif pic.startswith("/"):
        pic = HOST + pic
    return pic

# ===== 五方法 =====
async def home(params, context):
    classes = [{"type_id": t, "type_name": n} for t, n in CATEGORIES]
    sort_f = {"key": "sort", "name": "排序", "value": [
        {"n": "最新更新", "v": "latest"},
        {"n": "当前热播", "v": "hot"},
        {"n": "独家原创", "v": "original"},
        {"n": "随机推荐", "v": "random"},
    ]}
    ranks_f = {"key": "rank_type", "name": "榜单", "value": [
        {"n": "🔥 热播榜", "v": "hot"},
        {"n": "⭐ 推荐榜", "v": "recommend"},
        {"n": "🚀 潜力榜", "v": "potential"},
    ]}
    chigua_f = {"key": "cate", "name": "分类", "value": [
        {"n": "全部", "v": "all"},
        {"n": "热门吃瓜", "v": "remen"},
        {"n": "AI原创", "v": "yuanchuang"},
    ]}
    topics_f = {"key": "tid", "name": "话题", "value": [
        {"n": "🔥 热门AI短剧", "v": "hot-aiduanju"},
        {"n": "👻 paranormal", "v": "paranormal-aiduanju"},
        {"n": "🇪🇺 欧美短剧", "v": "oumei-duanju"},
        {"n": "🧠 天才男友", "v": "tiancai-nantong"},
        {"n": "✨ 魔法 Drama", "v": "magic-drama"},
        {"n": "⭐ 明星换脸", "v": "mingxing-huanlian"},
    ]}
    filters = {
        "ai-duanju": [sort_f], "ai-manju": [sort_f],
        "ai-huanlian": [sort_f], "ai-mogai": [sort_f],
        "ranks": [ranks_f], "chigua": [chigua_f], "topics": [topics_f],
    }
    videos = []
    try:
        data = await _get_json("/api/videos/category/ai-duanju",
                                {"page": 1, "size": PAGE_SIZE, "sort": "latest"})
        items = (data or {}).get("data", {}).get("items", [])
        for it in items:
            videos.append({
                "vod_id": str(it.get("id", "")),
                "vod_name": it.get("title", ""),
                "vod_pic": _norm_pic(it.get("cover", "")),
                "vod_remarks": _remarks(it),
            })
        await _enrich_pics(videos)
    except Exception as e:
        OmniBox.log("warn", "[黄果][home] 推荐失败: %s" % e)
    OmniBox.log("info", "[黄果][home] 分类=%d 列表=%d" % (len(classes), len(videos)))
    return {"class": classes, "filters": filters, "list": videos}

async def category(params, context):
    tid = str(params.get("categoryId") or params.get("tid") or "").strip()
    try:
        page = int(params.get("page") or 1)
    except Exception:
        page = 1
    if page < 1:
        page = 1
    filters = params.get("filters") if isinstance(params.get("filters"), dict) else {}
    result = {"list": [], "page": page, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}

    if tid == "recommend":
        data = await _get_json("/api/videos/category/ai-duanju",
                                {"page": page, "size": PAGE_SIZE, "sort": "latest"})
        items = (data or {}).get("data", {}).get("items", [])
        pg = (data or {}).get("data", {}).get("pagination", {})
        for it in items:
            result["list"].append({
                "vod_id": str(it.get("id", "")),
                "vod_name": it.get("title", ""),
                "vod_pic": _norm_pic(it.get("cover", "")),
                "vod_remarks": _remarks(it),
            })
        result["pagecount"] = int(pg.get("pages", 1) or 1)
        result["total"] = int(pg.get("total", len(items)) or 0)

    elif tid == "ranks":
        rank_type = str(filters.get("rank_type") or "hot")
        data = await _get_json("/api/ranks/%s" % rank_type,
                                {"page": page, "size": PAGE_SIZE})
        items = (data or {}).get("data", {}).get("items", [])
        for it in items:
            result["list"].append({
                "vod_id": str(it.get("video_id", "")),
                "vod_name": it.get("title", ""),
                "vod_pic": _norm_pic(it.get("cover", "")),
                "vod_remarks": "#%s %s%s" % (it.get("rank", ""),
                                            it.get("metric_label", ""),
                                            it.get("metric_value", "")),
            })
        result["pagecount"] = page + 1 if len(items) >= PAGE_SIZE else page
        result["total"] = len(items) * page

    elif tid == "chigua":
        cate = str(filters.get("cate") or "all")
        if cate == "remen":
            path = "/chigua/remen/" if page == 1 else "/chigua/remen/page/%d/" % page
        elif cate == "yuanchuang":
            path = "/chigua/yuanchuang/" if page == 1 else "/chigua/yuanchuang/page/%d/" % page
        else:
            path = "/chigua/" if page == 1 else "/chigua/page/%d/" % page
        html = await _html(HOST + path)
        for m in re.finditer(
                r'<a[^>]*class="hg-post-card"[^>]*href="(/archives/(\d+)/)"[^>]*>([\s\S]{0,1500}?)</a>', html):
            href, pid, chunk = m.group(1), m.group(2), m.group(3)
            tm = re.search(r'<h3>(.*?)</h3>', chunk, re.S)
            title = re.sub(r'<[^>]+>', '', tm.group(1)).strip() if tm else ""
            pm = re.search(r'data-src="(https?://[^"]+)"', chunk) or re.search(r'src="(https?://[^"]+)"', chunk)
            result["list"].append({
                "vod_id": "archives_%s" % pid,
                "vod_name": title,
                "vod_pic": _norm_pic(pm.group(1) if pm else ""),
                "vod_remarks": "吃瓜",
            })
        pm2 = re.search(r'data-pages="(\d+)"', html)
        result["pagecount"] = int(pm2.group(1)) if pm2 else (page if len(result["list"]) < 12 else page + 1)
        result["total"] = len(result["list"])

    elif tid == "topics":
        topic = str(filters.get("tid") or "")
        if not topic:
            html = await _html(HOST + "/topics/")
        else:
            html = await _html("%s/topics/%s/%s" % (HOST, topic,
                                                    "?page=%d" % page if page > 1 else ""))
        for c in re.split(r'<div[^>]*class="hg-drama-card"', html or "")[1:]:
            lm = re.search(r'href="/detail/(\d+)/"', c)
            if not lm:
                continue
            pid = lm.group(1)
            tm = re.search(r'hg-drama-card__title[^>]*><a[^>]*>([^<]+)</a>', c)
            title = tm.group(1).strip() if tm else "视频%s" % pid
            pm = re.search(r'data-src="(https?://[^"]+)"', c) or re.search(r'src="(https?://[^"]+)"', c)
            em = re.search(r'hg-drama-card__episode[^>]*>([^<]+)', c)
            result["list"].append({
                "vod_id": pid,
                "vod_name": title,
                "vod_pic": _norm_pic(pm.group(1) if pm else ""),
                "vod_remarks": em.group(1).strip() if em else "",
            })
        pm2 = re.search(r'data-pages="(\d+)"', html or "")
        result["pagecount"] = int(pm2.group(1)) if pm2 else (page if len(result["list"]) < PAGE_SIZE else page + 1)
        result["total"] = len(result["list"])

    else:
        # ai-duanju / ai-manju / ai-huanlian / ai-mogai
        sort = str(filters.get("sort") or "latest")
        if sort == "original":
            sort = "hot"
        if sort == "random":
            data = await _get_json("/api/videos/category/%s" % tid,
                                    {"page": 1, "size": PAGE_SIZE, "sort": "random"})
            items = (data or {}).get("data", {}).get("items", [])
            for it in items:
                result["list"].append({
                    "vod_id": str(it.get("id", "")),
                    "vod_name": it.get("title", ""),
                    "vod_pic": _norm_pic(it.get("cover", "")),
                    "vod_remarks": _remarks(it),
                })
            result["pagecount"] = 1
            result["total"] = len(items)
        else:
            data = await _get_json("/api/videos/category/%s" % tid,
                                    {"page": page, "size": PAGE_SIZE, "sort": sort})
            items = (data or {}).get("data", {}).get("items", [])
            pg = (data or {}).get("data", {}).get("pagination", {})
            for it in items:
                result["list"].append({
                    "vod_id": str(it.get("id", "")),
                    "vod_name": it.get("title", ""),
                    "vod_pic": _norm_pic(it.get("cover", "")),
                    "vod_remarks": _remarks(it),
                })
            result["pagecount"] = int(pg.get("pages", 1) or 1)
            result["total"] = int(pg.get("total", len(items)) or 0)

    await _enrich_pics(result["list"])
    OmniBox.log("info", "[黄果][category] tid=%s page=%d list=%d pc=%d" %
                (tid[:20], page, len(result["list"]), result["pagecount"]))
    return result

def _parse_ep_sources(html):
    """从详情页 HTML 提 epPlaySrcs: {集数: m3u8}"""
    eps = {}
    for m in re.finditer(r'"epPlaySrcs"\s*:\s*(\{[^}]+\})', html or ""):
        try:
            raw = m.group(1).replace("\\u0026", "&")
            data = json.loads(raw)
            for ep, src in data.items():
                src = str(src or "").replace("\\u0026", "&")
                if src.startswith("//"):
                    src = "https:" + src
                if src and ep not in eps:
                    eps[ep] = src
        except Exception:
            pass
    if not eps:
        m = re.search(r'"videoSrc"\s*:\s*"((?:https?://)?[^"]+)"', html or "")
        if m:
            src = m.group(1).replace("\\u0026", "&")
            if src.startswith("//"):
                src = "https:" + src
            eps["1"] = src
    return eps

async def detail(params, context):
    vid = str(params.get("videoId") or params.get("id") or "").strip()
    if not vid:
        return {"list": []}
    # 吃瓜文章
    if vid.startswith("archives_"):
        pid = vid.replace("archives_", "")
        html = await _html(HOST + "/archives/%s/" % pid)
        tm = re.search(r'<title>(.*?)</title>', html, re.S)
        title = (re.sub(r"\s+", " ", tm.group(1)).replace(" - 黄果短剧", "").strip()) if tm else "吃瓜%s" % pid
        pm = re.search(r'data-src="(https?://[^"]+)"', html) or re.search(r'src="(https?://[^"]+)"', html)
        pic = _norm_pic(pm.group(1) if pm else "")
        vurl = ""
        m = re.search(r'<video[^>]+src="(https?://[^"]+)"', html)
        if m:
            vurl = m.group(1)
        if not vurl:
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
            if m:
                vurl = m.group(1).replace("\\u0026", "&")
        await _enrich_pics([{"vod_pic": pic}])
        pic = (await _resolve_pic(pic)) if pic else ""
        return {"list": [{
            "vod_id": vid, "vod_name": title, "vod_pic": pic,
            "vod_content": "吃瓜内容",
            "vod_play_sources": [{
                "name": "黄果短剧",
                "episodes": [{"name": "阅读", "playId": "archives_%s@0" % pid, "url": vurl}]
            }],
        }]}

    html = await _html(HOST + "/video/%s/" % vid)
    if not html:
        return {"list": []}
    tm = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = tm.group(1).strip() if tm else vid
    title = re.sub(r"\s*第\s*\d+\s*集\s*$", "", title).strip()
    cm = re.search(r'data-src="(https?://[^"]+)"', html) or re.search(r'src="(https?://[^"]+)"', html)
    pic = _norm_pic(cm.group(1) if cm else "")
    dm = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    desc = (dm.group(1) if dm else "").strip()
    eps = _parse_ep_sources(html)
    if not eps:
        eps = {"1": vid}  # 兜底
    episodes = []
    for ep in sorted(eps.keys(), key=lambda x: int(re.search(r"\d+", str(x)).group()) if re.search(r"\d+", str(x)) else 0):
        episodes.append({
            "name": "第%s集" % ep,
            "playId": "%s@%s" % (vid, ep),
        })
    await _enrich_pics([{"vod_pic": pic}])
    pic = await _resolve_pic(pic) if pic else ""
    OmniBox.log("info", "[黄果][detail] id=%s name=%s eps=%d" % (vid, title[:20], len(episodes)))
    return {"list": [{
        "vod_id": vid, "vod_name": title, "vod_pic": pic,
        "vod_content": desc,
        "vod_remarks": "",
        "vod_play_sources": [{
            "name": "黄果短剧",
            "episodes": episodes,
        }],
    }]}

async def search(params, context):
    keyword = str(params.get("keyword") or "").strip()
    try:
        page = int(params.get("page") or 1)
    except Exception:
        page = 1
    if page < 1:
        page = 1
    result = {"list": [], "page": page, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
    if not keyword:
        return result
    # /search/?keyword= -> 301 -> /search/video/{kw}/
    path = "/search/video/%s/" % quote(keyword, safe="")
    if page > 1:
        path += "?page=%d" % page
    html = await _html(HOST + path)
    seen = set()
    for m in re.finditer(r'data-track-id="(\d+)"', html or ""):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        chunk = html[m.start():m.start() + 800]
        tm = re.search(r'data-track-title="([^"]*)"', chunk)
        pm = re.search(r'data-src="(https?://[^"]*)"', chunk) or re.search(r'src="(https?://[^"]*)"', chunk)
        result["list"].append({
            "vod_id": vid,
            "vod_name": tm.group(1) if tm else "",
            "vod_pic": _norm_pic(pm.group(1) if pm else ""),
            "vod_remarks": "",
        })
    tm2 = re.search(r'data-track-search-total="(\d+)"', html or "")
    pm2 = re.search(r'data-pages="(\d+)"', html or "")
    if tm2:
        result["total"] = int(tm2.group(1))
    result["pagecount"] = int(pm2.group(1)) if pm2 else (page + 1 if len(result["list"]) >= PAGE_SIZE else page)
    await _enrich_pics(result["list"])
    OmniBox.log("info", "[黄果][search] kw=%s page=%d list=%d" % (keyword[:15], page, len(result["list"])))
    return result

async def play(params, context):
    play_id = str(params.get("playId") or "").strip()
    if not play_id:
        return {"urls": [], "flag": "", "header": {}}
    # archives 吃瓜
    if play_id.startswith("archives_"):
        pid = play_id.split("@", 1)[0].replace("archives_", "")
        html = await _html(HOST + "/archives/%s/" % pid)
        vurl = ""
        m = re.search(r'<video[^>]+src="(https?://[^"]+)"', html)
        if m:
            vurl = m.group(1)
        if not vurl:
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
            if m:
                vurl = m.group(1).replace("\\u0026", "&")
        if vurl:
            return {"urls": [{"name": "播放", "url": vurl}], "flag": "",
                    "header": {"User-Agent": UA, "Referer": HOST + "/"}}
        return {"urls": [], "flag": "", "header": {}}
    # 普通视频: vid@ep
    parts = play_id.split("@", 1)
    vid = parts[0]
    ep = parts[1] if len(parts) > 1 else "1"
    html = await _html(HOST + "/video/%s/" % vid)
    eps = _parse_ep_sources(html)
    url = eps.get(ep) or eps.get("1") or ""
    if not url:
        # 兜底: 直接当 vid 走 API
        data = await _get_json("/api/videos/detail/%s" % vid)
        url = (data.get("data") or {}).get("videoSrc", "")
    if url:
        url = url.replace("\\u0026", "&")
    OmniBox.log("info", "[黄果][play] id=%s ep=%s url=%s" % (vid, ep, url[:80]))
    return {
        "urls": [{"name": "播放", "url": url}] if url else [],
        "flag": "",
        "header": {"User-Agent": UA, "Referer": HOST + "/"},
    }

# ===== OmniBox 注册 (模块顶层, 必须在 if __name__ 之前) =====
HANDLERS = {"home": home, "category": category, "detail": detail, "search": search, "play": play}
run(HANDLERS)

# ===== 本地自测 =====
if __name__ == "__main__":
    import asyncio as _aio

    async def _main():
        print("=== home ===")
        h = await home({}, {})
        print("class:", [c["type_name"] for c in h["class"]])
        print("list:", len(h["list"]))
        for v in h["list"][:3]:
            print("  ", v["vod_id"], v["vod_name"][:20], "|", v["vod_pic"][:50])

        print("\n=== category ai-duanju p1 ===")
        c = await category({"categoryId": "ai-duanju", "page": 1}, {})
        print("list:", len(c["list"]), "pc:", c["pagecount"], "total:", c["total"])
        for v in c["list"][:3]:
            print("  ", v["vod_id"], v["vod_name"][:20], "|", v["vod_remarks"], "|", v["vod_pic"][:50])

        print("\n=== category ranks/hot ===")
        r = await category({"categoryId": "ranks", "page": 1, "filters": {"rank_type": "hot"}}, {})
        print("list:", len(r["list"]))
        for v in r["list"][:3]:
            print("  ", v["vod_id"], v["vod_name"][:20], "|", v["vod_remarks"])

        print("\n=== detail ===")
        if c["list"]:
            vid = c["list"][0]["vod_id"]
            d = await detail({"videoId": vid}, {})
            if d["list"]:
                it = d["list"][0]
                print("name:", it["vod_name"])
                print("pic:", it["vod_pic"][:60])
                eps = it["vod_play_sources"][0]["episodes"] if it.get("vod_play_sources") else []
                print("eps:", len(eps), eps[0] if eps else "")
                print("\n=== play ===")
                if eps:
                    p = await play({"playId": eps[0]["playId"]}, {})
                    print("urls:", p.get("urls"))

        print("\n=== search ===")
        s = await search({"keyword": "囚笼", "page": 1}, {})
        print("list:", len(s["list"]), "total:", s["total"])
        for v in s["list"][:3]:
            print("  ", v["vod_id"], v["vod_name"][:20])

    _aio.run(_main())
