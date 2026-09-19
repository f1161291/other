# -*- coding: utf-8 -*-
# @name 91Porn
# @version 1.0.0
# @downloadURL https://github.com/Silent1566/OmniBox-Spider/raw/main/影视/采集/91porn.py
# @indexs 1
# @dependencies pyquery

import re
import urllib.parse
from pyquery import PyQuery as pq
from spider_runner import OmniBox, run

HOSTS = [
    'https://0708.fs708.com/',
    'https://a.91kp.net/',
    'https://91porn.com/'
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
        return f"https:{href}"
    return f"{host.rstrip('/')}/{href.lstrip('/')}"


def is_video_format(url):
    return any(ext in (url or '').lower() for ext in ['.m3u8', '.mp4', '.ts'])


async def fetch_url(url, host, params=None, timeout=15):
    for target_host in HOSTS:
        target_url = url
        for old_host in HOSTS:
            if old_host in target_url:
                target_url = target_url.replace(old_host, target_host)
                break
        else:
            if not target_url.startswith('http'):
                target_url = f"{target_host.rstrip('/')}/{target_url.lstrip('/')}"

        headers = {**HEADERS, 'Referer': target_host}
        try:
            res = await OmniBox.request(target_url, {
                'method': 'GET',
                'headers': headers,
            })
            if res.get('statusCode') == 200 and len(res.get('body', '').strip()) > 0:
                return res.get('body', ''), target_host
        except Exception as e:
            await OmniBox.log('warn', f'[fetch] {target_host} 失败: {e}')

    return '', host


def parse_video_items(data, host):
    vlist = []
    seen_ids = set()

    containers = data('div[class*="col-xs-12"]').items()

    for container in containers:
        try:
            container_class = (container.attr('class') or '').lower()
            if 'col-lg-8' in container_class or 'ad' in container_class or 'sponsor' in container_class:
                continue

            item = container('.well.well-sm, .videos-text-align')
            if not item:
                item = container

            a_elem = item('a[href*="view_video.php"]')
            if not a_elem:
                continue

            href = abs_href(a_elem.attr('href'), host)

            if not href or 'viewkey=' not in href:
                continue

            vk_match = re.search(r'viewkey=([a-zA-Z0-9]+)', href)
            vk_id = vk_match.group(1) if vk_match else href

            if vk_id in seen_ids:
                continue

            title_elem = item('span[class*="video-title"], .video-title')
            title = title_elem.text().strip()
            if not title:
                title = a_elem.attr('title') or a_elem.text().strip()
            if not title or any(ad_kw in title.lower() for ad_kw in ['广告', 'sponsor', '推广', '赞助']):
                continue

            pic = ''
            img_elem = item('img')
            if img_elem:
                pic = (
                    img_elem.attr('data-src') or
                    img_elem.attr('data-original') or
                    img_elem.attr('src') or ''
                )

            if not pic:
                style = item('.img-responsive, .video-img, div[style*="background"]').attr('style') or ''
                if 'background' in style and 'url(' in style:
                    bg_m = re.search(r'url\([\'"]?([^\'"\)]+)[\'"]?\)', style)
                    if bg_m:
                        pic = bg_m.group(1)

            if 'loading' in pic or 'blank' in pic or 'default' in pic:
                pic = ''

            pic = abs_href(pic, host) if pic else ''

            duration = item('.duration').text().strip() or '未知'

            seen_ids.add(vk_id)
            vlist.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': duration
            })
        except Exception:
            continue

    return vlist


def parse_pagecount(data):
    try:
        nums = []
        for a in data('a').items():
            m = re.search(r'[?&]page=(\d+)', a.attr('href') or '')
            if m:
                nums.append(int(m.group(1)))
        if nums:
            return max(nums)

        page_nums = []
        for a in data('.pagination li a, .pagingnav a').items():
            txt = a.text().strip()
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

    ad_keywords = ['ad-i18n-dsp', 'kwai.net', 'googleads', 'popads', 'doubleclick', 'analytics', 'preview', 'cover']

    all_urls = re.findall(r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*', html, re.I)
    for url in all_urls:
        url_clean = url.replace('&amp;', '&').strip()
        if any(ad in url_clean.lower() for ad in ad_keywords):
            continue
        if any(kw in url_clean.lower() for kw in ['st=', 'key=', 'secure=', 'token=', 'cdn', 'get_file']):
            return url_clean

    for url in all_urls:
        url_clean = url.replace('&amp;', '&').strip()
        if not any(ad in url_clean.lower() for ad in ad_keywords):
            return url_clean

    return None


def extract_vid(text):
    patterns = [
        r'viewkey=([a-zA-Z0-9]+)',
        r'/viewvideo\.php\?.*viewkey=([a-zA-Z0-9]+)',
        r'VID["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]+)',
        r'/ev\.php\?VID=([a-zA-Z0-9]+)'
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def get_ev_url(html, detail_url, host):
    m = re.search(r'<textarea[^>]*>\s*(https?://[^<]+/ev\.php\?VID=[^<\s]+)', html, re.I)
    if m:
        return m.group(1).strip()

    matches = re.findall(r'(https?://[^"\'\s<>]+/ev\.php\?VID=[a-zA-Z0-9]+)', html, re.I)
    if matches:
        return matches[0]

    vid = extract_vid(html) or extract_vid(detail_url)
    if vid:
        return f"{host}ev.php?VID={vid}"
    return None


async def home(params, context):
    try:
        host = HOSTS[0]
        await OmniBox.log('info', '[home] 开始获取首页')

        html, host = await fetch_url(f"{host}index.php", host)
        if not html:
            return {'class': [], 'list': []}

        data = pq(html)
        vlist = parse_video_items(data, host)

        result = {
            'class': [{'type_name': k, 'type_id': v} for k, v in CLASS_MAP.items()],
            'list': vlist
        }

        await OmniBox.log('info', f'[home] 获取 {len(vlist)} 个视频')
        return result
    except Exception as e:
        await OmniBox.log('error', f'[home] 失败: {e}')
        return {'class': [], 'list': []}


async def category(params, context):
    try:
        category_id = params.get('categoryId', 'watch')
        page = params.get('page') or 1
        host = HOSTS[0]

        await OmniBox.log('info', f'[category] categoryId={category_id}, page={page}')

        if category_id == 'top_m':
            url = f"{host}v.php?category=top&m=-1&viewtype=basic&page={page}"
        else:
            url = f"{host}v.php?category={category_id}&viewtype=basic&page={page}"

        html, host = await fetch_url(url, host)
        if not html:
            return {'page': page, 'pagecount': 1, 'total': 0, 'list': []}

        data = pq(html)
        vlist = parse_video_items(data, host)
        pagecount = parse_pagecount(data)

        await OmniBox.log('info', f'[category] 获取 {len(vlist)} 个视频, 页数={pagecount}')
        return {
            'page': page,
            'pagecount': pagecount,
            'total': 999999,
            'list': vlist
        }
    except Exception as e:
        await OmniBox.log('error', f'[category] 失败: {e}')
        return {'page': 1, 'pagecount': 1, 'total': 0, 'list': []}


async def detail(params, context):
    try:
        vod_id = params.get('videoId')
        if not vod_id:
            return {'list': []}

        host = HOSTS[0]
        detail_url = vod_id if vod_id.startswith('http') else f"{host.rstrip('/')}/{vod_id.lstrip('/')}"

        await OmniBox.log('info', f'[detail] videoId={vod_id}')

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

        if not video_url:
            video_url = detail_url

        data = pq(html)
        title = data('title').text().strip().split('- 91porn')[0].strip() or '未知标题'
        pic = (data('meta[property="og:image"]').attr('content') or
               data('video#player_one').attr('poster') or
               data('.video-pic img, img.img-responsive').attr('src') or '')
        pic = abs_href(pic, host) if pic else ''

        duration = '未知'
        m_dur = re.search(r'\d{2}:\d{2}:\d{2}|\d{2}:\d{2}', html)
        if m_dur:
            duration = m_dur.group(0)

        views = '未知'
        main_box = data('div[class*="col-md-8"], .col-xs-12')
        for span in main_box.find('span.info').items():
            txt = span.text()
            if '热度' in txt or '观看' in txt:
                m = re.search(r'[\d]+', span.parent().text().strip())
                if m:
                    views = m.group(0)

        remarks = f"{duration} | 观看:{views}" if views != '未知' else duration

        await OmniBox.log('info', f'[detail] title={title}, video_url存在={bool(video_url)}')

        return {'list': [{
            'vod_id': vod_id,
            'vod_name': title,
            'vod_pic': pic,
            'vod_play_from': '91Porn',
            'vod_play_url': f'高清${video_url}',
            'vod_director': '91',
            'vod_remarks': remarks,
            'vod_content': title,
            'vod_play_sources': [{
                'name': '91Porn',
                'episodes': [{
                    'name': '高清',
                    'playId': video_url
                }]
            }]
        }]}
    except Exception as e:
        await OmniBox.log('error', f'[detail] 失败: {e}')
        return {'list': []}


async def search(params, context):
    try:
        keyword = (params.get('keyword') or params.get('wd') or '').strip()
        page = params.get('page') or 1

        if not keyword:
            return {'page': 1, 'pagecount': 0, 'total': 0, 'list': []}

        host = HOSTS[0]
        await OmniBox.log('info', f'[search] keyword={keyword}, page={page}')

        encoded_key = urllib.parse.quote(keyword)
        url = f"{host}search_result.php?search_id={encoded_key}&search_type=search_videos&min_duration=&page={page}"

        html, host = await fetch_url(url, host)
        if not html:
            return {'page': page, 'pagecount': 1, 'total': 0, 'list': []}

        data = pq(html)
        vlist = parse_video_items(data, host)

        if not vlist:
            return {'page': page, 'pagecount': 1, 'total': 0, 'list': []}

        pagecount = parse_pagecount(data) or (page + 1)

        await OmniBox.log('info', f'[search] 获取 {len(vlist)} 个结果')
        return {
            'page': page,
            'pagecount': pagecount,
            'total': 999999,
            'list': vlist
        }
    except Exception as e:
        await OmniBox.log('error', f'[search] 失败: {e}')
        return {'page': 1, 'pagecount': 1, 'total': 0, 'list': []}


async def play(params, context):
    try:
        play_id = params.get('playId')
        flag = params.get('flag') or '91Porn'

        if not play_id:
            return {'urls': [], 'flag': flag, 'header': {}, 'parse': 0}

        await OmniBox.log('info', f'[play] playId={play_id}')

        header = {
            'User-Agent': HEADERS.get('User-Agent'),
            'Referer': f"{HOSTS[0].rstrip('/')}/"
        }

        parse = 0 if is_video_format(play_id) else 1

        return {
            'urls': [{'name': '播放', 'url': play_id}],
            'flag': flag,
            'header': header,
            'parse': parse
        }
    except Exception as e:
        await OmniBox.log('error', f'[play] 失败: {e}')
        return {'urls': [], 'flag': params.get('flag', ''), 'header': {}, 'parse': 0}


if __name__ == '__main__':
    run({
        'home': home,
        'category': category,
        'detail': detail,
        'search': search,
        'play': play
    })
