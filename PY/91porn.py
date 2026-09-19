# -*- coding: utf-8 -*-
# @name 91Porn
# @version 1.7.0
# @downloadURL https://github.com/Silent1566/OmniBox-Spider/raw/main/影视/采集/91porn.py
# @dependencies lxml

import re
import json
import urllib.parse
from lxml import etree
from spider_runner import OmniBox, run

HOSTS = [
    'https://a.91kp.net/',
    'https://91porn.com/',
    'https://0708.fs708.com/'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}

CLASS_MAP = {
    '最新': 'watch',
    '91原创': 'ori',
    '当前最热': 'hot',
    '本月最热': 'top',
    '10分钟以上': 'long',
    '20分钟以上': 'longer',
    '本月收藏': 'tf',
    '最近加精': 'rf',
    '高清': 'hd',
    '每月最热': 'top_m',
    '本月讨论': 'md',
    '收藏最多': 'mf'
}


def abs_href(href, host):
    if not href:
        return ''
    if href.startswith('http'):
        return href
    if href.startswith('//'):
        return 'https:' + href
    return host.rstrip('/') + '/' + href.lstrip('/')


def is_video_format(url):
    return any(ext in (url or '').lower() for ext in ['.m3u8', '.mp4', '.ts'])


def extract_viewkey(url):
    m = re.search(r'viewkey=([a-zA-Z0-9]+)', url or '')
    return m.group(1) if m else ''


async def fetch_url(url, host, timeout=15):
    for target_host in HOSTS:
        target_url = url
        for old_host in HOSTS:
            if old_host in target_url:
                target_url = target_url.replace(old_host, target_host)
                break
        else:
            if not target_url.startswith('http'):
                target_url = target_host.rstrip('/') + '/' + target_url.lstrip('/')
        headers = dict(HEADERS)
        headers['Referer'] = target_host
        try:
            res = await OmniBox.request(target_url, {
                'method': 'GET',
                'headers': headers,
            })
            if res.get('statusCode') == 200 and len(res.get('body', '').strip()) > 0:
                return res.get('body', ''), target_host
        except Exception:
            pass
    return '', host


def parse_html(text):
    try:
        return etree.HTML(text or '')
    except Exception:
        return None


def get_text(node):
    if node is None:
        return ''
    return (node.text_content() or '').strip()


def parse_video_items(root, host):
    vlist = []
    if root is None:
        return vlist
    seen_ids = set()
    for a in root.xpath('//a[contains(@href, "view_video.php")]'):
        try:
            href = abs_href(a.get('href') or '', host)
            if not href or 'viewkey=' not in href:
                continue
            vk_id = extract_viewkey(href)
            if not vk_id or vk_id in seen_ids:
                continue
            title = ''
            title_attr = a.get('title')
            if title_attr:
                title = title_attr.strip()
            if not title:
                parent = a.getparent()
                if parent is not None:
                    for span in parent.xpath('.//span'):
                        cls = span.get('class') or ''
                        if 'video-title' in cls:
                            title = (span.text or '').strip()
                            break
            if not title:
                imgs = a.xpath('.//img')
                if imgs:
                    alt = imgs[0].get('alt')
                    if alt:
                        title = alt.strip()
            if not title:
                continue
            pic = ''
            imgs = a.xpath('.//img')
            if imgs:
                img = imgs[0]
                pic = img.get('data-src') or img.get('data-original') or img.get('src') or ''
            if pic and ('loading' in pic or 'blank' in pic or 'default' in pic):
                pic = ''
            if pic:
                pic = abs_href(pic, host)
            duration = '未知'
            parent = a.getparent()
            if parent is not None:
                for el in parent.xpath('.//*[contains(@class, "duration")]'):
                    t = (el.text or '').strip()
                    if t:
                        duration = t
                        break
            seen_ids.add(vk_id)
            vlist.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': duration,
                'style': {'type': 'rect', 'ratio': 1.33}
            })
        except Exception:
            continue
    return vlist


def parse_pagecount(root):
    try:
        if root is None:
            return 1
        nums = []
        for a in root.xpath('//a'):
            href = a.get('href', '')
            m = re.search(r'[?&]page=(\d+)', href)
            if m:
                nums.append(int(m.group(1)))
        if nums:
            return max(nums)
        page_nums = []
        for a in root.xpath('//*[contains(@class, "pagination")]//a | //*[contains(@class, "pagingnav")]//a'):
            txt = get_text(a)
            if txt.isdigit():
                page_nums.append(int(txt))
        return max(page_nums) if page_nums else 1
    except Exception:
        return 1


def extract_video_url_from_html(html, host):
    if not html:
        return None
    encode_matches = re.findall(r'strencode2\((?:["\'])(.*?)(?:["\'])\)', html)
    for enc_str in encode_matches:
        decoded_tag = urllib.parse.unquote(enc_str)
        src_m = re.search(r"src=['\"]([^'\"]+)['\"]", decoded_tag, re.I)
        if src_m:
            real_url = src_m.group(1).replace('&amp;', '&').strip()
            if is_video_format(real_url):
                return abs_href(real_url, host)
    ad_kw = ['ad-i18n-dsp', 'kwai.net', 'googleads', 'popads', 'doubleclick', 'analytics', 'preview', 'cover']
    all_urls = re.findall(r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*', html, re.I)
    for url in all_urls:
        u = url.replace('&amp;', '&').strip()
        if any(ad in u.lower() for ad in ad_kw):
            continue
        if any(kw in u.lower() for kw in ['st=', 'key=', 'secure=', 'token=', 'cdn', 'get_file']):
            return u
    for url in all_urls:
        u = url.replace('&amp;', '&').strip()
        if not any(ad in u.lower() for ad in ad_kw):
            return u
    return None


def extract_vid(text):
    for p in [r'viewkey=([a-zA-Z0-9]+)', r'VID["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]+)', r'/ev\.php\?VID=([a-zA-Z0-9]+)']:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None


def get_ev_url(html, detail_url, host):
    m = re.search(r'<textarea[^>]*>\s*(https?://[^<]+/ev\.php\?VID=[^<\s]+)', html, re.I)
    if m:
        return m.group(1).strip()
    vid = extract_vid(html) or extract_vid(detail_url)
    if vid:
        return host + 'ev.php?VID=' + vid
    return None


async def home(params, context):
    try:
        host = HOSTS[0]
        html, host = await fetch_url(host + 'index.php', host)
        if not html:
            return {'class': [{'type_name': k, 'type_id': v} for k, v in CLASS_MAP.items()], 'list': []}
        root = parse_html(html)
        vlist = parse_video_items(root, host)
        return {
            'class': [{'type_name': k, 'type_id': v} for k, v in CLASS_MAP.items()],
            'list': vlist or []
        }
    except Exception:
        return {'class': [{'type_name': k, 'type_id': v} for k, v in CLASS_MAP.items()], 'list': []}


async def category(params, context):
    try:
        tid = params.get('categoryId', 'watch')
        pg = params.get('page') or 1
        host = HOSTS[0]
        if tid == 'top_m':
            url = host + 'v.php?category=top&m=-1&viewtype=basic&page=' + str(pg)
        else:
            url = host + 'v.php?category=' + tid + '&viewtype=basic&page=' + str(pg)
        html, host = await fetch_url(url, host)
        if not html:
            return {'page': pg, 'pagecount': 1, 'total': 0, 'list': []}
        root = parse_html(html)
        vlist = parse_video_items(root, host)
        pc = parse_pagecount(root)
        return {'page': pg, 'pagecount': pc, 'total': 999999, 'list': vlist or []}
    except Exception:
        return {'page': 1, 'pagecount': 1, 'total': 0, 'list': []}


async def detail(params, context):
    try:
        vod_id = params.get('videoId')
        if not vod_id:
            return {'list': []}
        host = HOSTS[0]
        vid = str(vod_id).strip()
        vk = extract_viewkey(vid)
        if vk:
            detail_url = host + 'view_video.php?viewkey=' + vk
        elif vid.startswith('http'):
            detail_url = vid
        else:
            detail_url = host + vid
        html, host = await fetch_url(detail_url, host)
        if not html:
            return {'list': []}
        video_url = extract_video_url_from_html(html, host)
        if not video_url:
            ev_url = get_ev_url(html, detail_url, host)
            if ev_url:
                ev_html, _ = await fetch_url(ev_url, host)
                if ev_html:
                    video_url = extract_video_url_from_html(ev_html, host)
        root = parse_html(html)
        title = ''
        if root is not None:
            title_elems = root.xpath('//title')
            if title_elems:
                t = (title_elems[0].text or '').strip()
                title = t.split('- 91porn')[0].strip()
        if not title:
            title = 'unknown'
        pic = ''
        if root is not None:
            og_imgs = root.xpath('//meta[@property="og:image"]/@content')
            if og_imgs:
                pic = og_imgs[0]
            if not pic:
                vid_imgs = root.xpath('//video[@id="player_one"]/@poster')
                if vid_imgs:
                    pic = vid_imgs[0]
            if not pic:
                pic_imgs = root.xpath('//*[contains(@class, "video-pic")]//img/@src | //img[contains(@class, "img-responsive")]/@src')
                if pic_imgs:
                    pic = pic_imgs[0]
        pic = abs_href(pic, host) if pic else ''
        duration = 'unknown'
        m_dur = re.search(r'\d{2}:\d{2}:\d{2}|\d{2}:\d{2}', html)
        if m_dur:
            duration = m_dur.group(0)
        play_url = video_url if video_url else detail_url
        episodes = [{'name': duration, 'playId': play_url}]
        return {'list': [{
            'vod_id': vk or vid,
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': duration,
            'vod_content': title,
            'vod_play_sources': [{
                'name': '91Porn',
                'episodes': episodes
            }]
        }]}
    except Exception:
        return {'list': []}


async def search(params, context):
    try:
        keyword = (params.get('keyword') or params.get('wd') or '').strip()
        pg = params.get('page') or 1
        if not keyword:
            return {'page': 1, 'pagecount': 0, 'total': 0, 'list': []}
        host = HOSTS[0]
        safe_kw = re.sub(r'[^\w\s]', '', keyword)
        encoded_key = urllib.parse.quote(safe_kw or keyword)
        url = host + 'search_result.php?search_id=' + encoded_key + '&search_type=search_videos&page=' + str(pg)
        html, host = await fetch_url(url, host)
        if not html:
            return {'page': pg, 'pagecount': 1, 'total': 0, 'list': []}
        root = parse_html(html)
        vlist = parse_video_items(root, host)
        pc = parse_pagecount(root) or (pg + 1) if vlist else 1
        return {'page': pg, 'pagecount': pc, 'total': len(vlist), 'list': vlist or []}
    except Exception:
        return {'page': 1, 'pagecount': 1, 'total': 0, 'list': []}


async def play(params, context):
    try:
        play_id = params.get('playId')
        flag = params.get('flag') or '91Porn'
        if not play_id:
            return {'urls': [], 'flag': flag, 'header': {}, 'parse': 0}
        header = {
            'User-Agent': HEADERS.get('User-Agent'),
            'Referer': HOSTS[0].rstrip('/') + '/',
        }
        if is_video_format(play_id):
            return {
                'urls': [{'name': 'Play', 'url': play_id}],
                'flag': flag,
                'header': header,
                'parse': 0
            }
        try:
            sniff = await OmniBox.sniff_video(play_id, header)
            if sniff and sniff.get('url'):
                return {
                    'urls': [{'name': 'Play', 'url': sniff['url']}],
                    'flag': flag,
                    'header': sniff.get('header') or header,
                    'parse': 0
                }
        except Exception:
            pass
        return {
            'urls': [{'name': 'Play', 'url': play_id}],
            'flag': flag,
            'header': header,
            'parse': 1
        }
    except Exception:
        return {'urls': [], 'flag': params.get('flag', ''), 'header': {}, 'parse': 0}


if __name__ == '__main__':
    run({
        'home': home,
        'category': category,
        'detail': detail,
        'search': search,
        'play': play
    })
