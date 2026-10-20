// @name Pornhub
// @author 宝宝巴士
// @description Pornhub 热门/最新/分类/搜索（视频/女优/频道），原 ForwardWidget p.js 适配 OmniBox
// @version 1.0.0
// @downloadURL https://gh-proxy.org/https://github.com/Silent1566/OmniBox-Spider/raw/refs/heads/main/综合/Pornhub.js
// @indexs 1

/**
 * ==========================================================================
 * Pornhub - OmniBox 爬虫脚本（新格式）
 * ==========================================================================
 * 数据来源: https://www.pornhub.com
 * 改编自: ForwardWidget 脚本 p.js v3.6（作者：宝宝巴士）
 * 站点特征:
 *   - 列表页 <li class="pcVideoListItem" data-video-vkey=...>
 *   - 播放页内嵌 var flashvars_XXX = {...} JSON，mediaDefinitions 里取 HLS 直链
 *   - 有 Cloudflare 防护，拦截时返回明确错误日志
 *   - 部分网络/地区 403，需代理；数据中心 IP 常被拒
 * 核心功能:
 *   - home: 4 个排序源 + 36 个分类，首页热门推荐
 *   - category: 排序源/数字分类/特殊路径（path:/hd 等）统一走分类
 *   - search: 视频/女优/频道三类搜索（类型/排序由环境变量控制）
 *   - detail: viewkey 解析 flashvars 多清晰度；女优/频道页转剧集列表
 *   - play: 按线路名(清晰度)选流，失败回退网页嗅探（parse=1）
 * 环境变量:
 *   - PH_HOST: 源站地址，默认 https://www.pornhub.com
 *   - PH_IMG_PROXY: 封面反代前缀，设空关闭，默认 https://ik.bug.qzz.io/img?url=
 *   - PH_SEARCH_TYPE: 搜索类型 video|pornstar|channel，默认 video
 *   - PH_SEARCH_SORT: 视频搜索排序 ""|mv|tr|lg|mr，默认最相关
 * ==========================================================================
 */

const OmniBox = require("omnibox_sdk");
const runner = require("spider_runner");

/**
 * 作用：导出 5 个标准 handler 并启动 runner。
 */
module.exports = { home, category, detail, search, play };
runner.run(module.exports);

// ==================== 站点配置 ====================

const HOST = String(process.env.PH_HOST || "https://www.pornhub.com").replace(/\/+$/, "");

/** 封面反代前缀（CDN 防盗链打不开时启用；设空字符串关闭） */
const IMG_PROXY =
  process.env.PH_IMG_PROXY !== undefined
    ? String(process.env.PH_IMG_PROXY)
    : "https://ik.bug.qzz.io/img?url=";

/** 搜索类型与排序（OmniBox search 只有 keyword/page，枚举参数改由环境变量提供） */
const SEARCH_TYPE = String(process.env.PH_SEARCH_TYPE || "video");
const SEARCH_SORT = String(process.env.PH_SEARCH_SORT || "");

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

/** 分类列表每页条数估算值，仅用于 total 估算 */
const PAGE_LIMIT = 20;

/** 4 个排序源（对应原脚本 4 个列表模块） */
const SORTS = [
  { type_id: "ht", type_name: "热门视频" },
  { type_id: "mr", type_name: "最新上传" },
  { type_id: "mv", type_name: "最多观看" },
  { type_id: "tr", type_name: "最高评分" },
];

/** 分类枚举（数字分类走 /video?c=N，path: 前缀走整路径） */
const CATEGORIES = [
  { type_id: "c111", type_name: "日本" },
  { type_id: "c1", type_name: "亚洲" },
  { type_id: "c3", type_name: "业余" },
  { type_id: "c4", type_name: "大屁股" },
  { type_id: "c8", type_name: "巨乳" },
  { type_id: "c9", type_name: "金发" },
  { type_id: "c11", type_name: "棕发" },
  { type_id: "c13", type_name: "口交" },
  { type_id: "c15", type_name: "内射" },
  { type_id: "c16", type_name: "颜射" },
  { type_id: "c17", type_name: "黑人" },
  { type_id: "c21", type_name: "硬核" },
  { type_id: "c23", type_name: "玩具" },
  { type_id: "c24", type_name: "公开" },
  { type_id: "c25", type_name: "黑人白人" },
  { type_id: "c26", type_name: "拉丁" },
  { type_id: "c27", type_name: "女同" },
  { type_id: "c28", type_name: "熟女 Mature" },
  { type_id: "c29", type_name: "MILF" },
  { type_id: "c35", type_name: "肛交" },
  { type_id: "c41", type_name: "POV" },
  { type_id: "c42", type_name: "红发" },
  { type_id: "c65", type_name: "三人行" },
  { type_id: "c69", type_name: "潮吹" },
  { type_id: "c78", type_name: "按摩" },
  { type_id: "c80", type_name: "轮奸" },
  { type_id: "c86", type_name: "卡通" },
  { type_id: "c115", type_name: "独家" },
  { type_id: "c138", type_name: "认证业余" },
  { type_id: "c59", type_name: "小胸" },
  { type_id: "c492", type_name: "独奏女" },
  { type_id: "c105", type_name: "60FPS" },
  { type_id: "path:/popularwithwomen", type_name: "热门女性" },
  { type_id: "path:/categories/teen", type_name: "Teen" },
  { type_id: "path:/hd", type_name: "HD" },
  { type_id: "path:/vr", type_name: "VR" },
  { type_id: "path:/categories/hentai", type_name: "Hentai" },
];

/** 站点固定请求头（年龄验证 Cookie 必带，缺了会跳验证页） */
function siteHeaders(referer) {
  return {
    "User-Agent": UA,
    Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    Referer: referer || HOST + "/",
    Cookie: "platform=pc; age_verified=1; accessAgeDisclaimerPH=1",
    "Accept-Encoding": "identity",
  };
}

// ==================== 通用工具 ====================

function log(level, message) {
  return OmniBox.log(level, `[Pornhub] ${message}`);
}

function t(v) {
  return String(v == null ? "" : v).trim();
}

/** 大小写不明的响应头里按名取值 */
function headerValue(headers, name) {
  if (!headers) return "";
  if (typeof headers.get === "function") {
    var v = headers.get(name);
    if (v != null) return String(v);
  }
  for (var k in headers) {
    if (String(k).toLowerCase() === name.toLowerCase()) return String(headers[k] || "");
  }
  return "";
}

function absUrl(u) {
  u = t(u);
  if (!u) return "";
  if (u.indexOf("//") === 0) return "https:" + u;
  if (u.indexOf("http") === 0) return u;
  if (u.charAt(0) === "/") return HOST + u;
  return HOST + "/" + u;
}

/** Cloudflare 拦截页判定 */
function isCF(html) {
  return /Just a moment|cf-browser-verification|challenge-platform/i.test(html || "");
}

/**
 * 函数：bodyToText
 * 作用：响应体规整为文本；压缩流（gzip/brotli）先解压。
 */
function bodyToText(body) {
  if (body == null) return "";
  if (typeof body === "string") return body;
  try {
    var zlib = require("zlib");
    var buf = Buffer.isBuffer(body) ? body : Buffer.from(body);
    if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
      try {
        return zlib.gunzipSync(buf).toString("utf-8");
      } catch (e) {}
    }
    try {
      return zlib.brotliDecompressSync(buf).toString("utf-8");
    } catch (e) {}
    return buf.toString("utf-8");
  } catch (e) {
    return String(body);
  }
}

/**
 * 函数：fetchHtml
 * 作用：统一请求页面。
 *   - 手动跟随 3xx 跳转（OmniBox.request 不跟随）
 *   - 压缩体解压、CF 拦截/404/403 识别，失败记录原因并返回 ""
 */
async function fetchHtml(url, referer) {
  var lastError = "";
  for (var attempt = 1; attempt <= 2; attempt++) {
    var current = url;
    var hops = 0;
    while (hops < 6) {
      hops++;
      try {
        var res = await OmniBox.request(current, {
          method: "GET",
          headers: siteHeaders(referer || HOST + "/"),
        });
        var status = Number(res && res.statusCode) || 0;
        var body = bodyToText(res && res.body);

        if (status === 404 || /<title>[^<]*404|Page Not Found/i.test(body.slice(0, 2000))) {
          await log("warn", `[请求] 404 url=${current}`);
          return "";
        }
        if (status >= 300 && status < 400) {
          var loc = headerValue(res && res.headers, "location");
          if (loc) {
            current = absUrl(loc);
            continue;
          }
          lastError = "HTTP " + status + "（缺少 Location）";
          break;
        }
        if (status >= 200 && status < 300 && body) {
          if (isCF(body)) {
            await log("error", `[请求] Cloudflare 拦截 url=${current}（需代理或稍后再试）`);
            return "";
          }
          return body;
        }
        if (status === 403) {
          await log("error", `[请求] 403 被拦截 url=${current}（数据中心 IP 常被拒，需代理）`);
          return "";
        }
        lastError = "HTTP " + status + " len=" + body.length;
        break;
      } catch (e) {
        lastError = (e && e.message) || String(e);
        break;
      }
    }
  }
  await log("error", `[请求] 失败 url=${url} 原因=${lastError}`);
  return "";
}

// ==================== 封面/卡片解析 ====================

/** 封面统一走反代（CDN 防盗链）；过滤 webm 预览与静态资源 */
function wrapCover(u) {
  u = absUrl(u);
  if (!u) return "";
  if (/\.webm(\?|$)/i.test(u)) return "";
  if (/www-static|\.js(\?|$)/i.test(u)) return "";
  var proxy = t(IMG_PROXY);
  if (proxy && u.indexOf(proxy) !== 0 && !/\/img\?url=/i.test(u)) {
    if (/url=$/i.test(proxy)) return proxy + encodeURIComponent(u);
    return proxy.replace(/\/$/, "") + "/img?url=" + encodeURIComponent(u);
  }
  return u;
}

/** 从视频卡片里按优先级取封面（多字段 + data-path CDN 拼接兜底） */
function pickCoverFromCard(cardHtml) {
  function attr(name) {
    var m = cardHtml.match(new RegExp(name + '="([^"]+)"', "i"));
    return m ? m[1] : "";
  }
  var candidates = [
    attr("data-mediumthumb"),
    attr("data-image"),
    attr("data-src"),
    attr("data-thumb_url"),
    attr("src"),
  ];
  var path = attr("data-path");
  if (path) {
    path = path.replace(/\{index\}/gi, "1");
    if (path.charAt(0) === "/") {
      candidates.push("https://pix-cdn77.phncdn.com" + path);
      candidates.push("https://ei.phncdn.com" + path);
    }
  }
  for (var i = 0; i < candidates.length; i++) {
    var u = wrapCover(candidates[i]);
    if (u) return u;
  }
  var m = cardHtml.match(/https?:\/\/[^"'\s]+phncdn\.com[^"'\s]+\.(?:jpg|jpeg|png|webp)[^"'\s]*/i);
  return m ? wrapCover(m[0]) : "";
}

function pickTitleFromCard(cardHtml) {
  var m = cardHtml.match(/\btitle="([^"]{2,})"/i);
  if (m && m[1].indexOf("http") < 0) return t(m[1]);
  m = cardHtml.match(/\balt="([^"]{2,})"/i);
  return m ? t(m[1]) : "";
}

function pickDurationFromCard(cardHtml) {
  var m = cardHtml.match(/class="[^"]*duration[^"]*"[^>]*>([^<]+)/i);
  return m ? t(m[1]) : "";
}

function extractViewkey(s) {
  var m = String(s || "").match(/viewkey=([a-zA-Z0-9]+)/i);
  return m ? m[1] : "";
}

/**
 * 函数：parseVideoList
 * 作用：列表页 HTML → 视频 VodItem 数组（按 viewkey 去重）。
 */
function parseVideoList(html) {
  var results = [];
  var seen = {};
  var parts = String(html || "").split(/<li(?=[^>]*\bpcVideoListItem\b)/i);
  for (var i = 1; i < parts.length; i++) {
    var card = "<li" + parts[i].split(/<\/li>/i)[0] + "</li>";
    var m = card.match(/data-video-vkey="([a-zA-Z0-9]+)"/i);
    var viewkey = m ? m[1] : extractViewkey(card);
    if (!viewkey || seen[viewkey]) continue;
    seen[viewkey] = true;
    var title = pickTitleFromCard(card) || viewkey;
    var cover = pickCoverFromCard(card);
    var durationText = pickDurationFromCard(card);
    results.push({
      vod_id: viewkey,
      vod_name: title,
      vod_pic: cover,
      vod_cover: cover,
      vod_remarks: durationText,
      vod_content: durationText ? "时长 " + durationText : "",
      type_id: "",
      type_name: "",
    });
  }
  return results;
}

/** 女优搜索结果：phstar:slug，detail 时展开为视频剧集 */
function parsePornstarList(html) {
  var out = [];
  var seen = {};
  var parts = String(html || "").split(/href="(\/pornstar\/[a-zA-Z0-9\-]+)"/i);
  for (var i = 1; i < parts.length; i += 2) {
    var slug = parts[i].replace(/^\/pornstar\//, "");
    if (!slug || seen[slug]) continue;
    seen[slug] = 1;
    var chunk = parts[i + 1] ? parts[i + 1].slice(0, 1000) : "";
    var title = slug.replace(/-/g, " ");
    var tm = /(?:title|alt)="([^"]+)"/i.exec(chunk) || /class="[^"]*title[^"]*"[^>]*>([^<]+)/i.exec(chunk);
    if (tm) title = t(tm[1]);
    var cover = "";
    var cm =
      /(?:data-src|data-thumb|src)="(https?:\/\/[^"]+phncdn[^"]+)"/i.exec(chunk) ||
      /(?:data-src|src)="(https?:\/\/[^"]+\.(?:jpg|png|webp)[^"]*)"/i.exec(chunk);
    if (cm) cover = wrapCover(cm[1]);
    out.push({
      vod_id: "phstar:" + slug,
      vod_name: "女优 · " + title,
      vod_pic: cover,
      vod_cover: cover,
      vod_remarks: "女优主页",
    });
    if (out.length >= 40) break;
  }
  return out;
}

/** 频道/片商搜索结果：phch:slug */
function parseChannelList(html) {
  var out = [];
  var seen = {};
  var parts = String(html || "").split(/href="(\/channels\/[a-zA-Z0-9\-]+)"/i);
  for (var i = 1; i < parts.length; i += 2) {
    var slug = parts[i].replace(/^\/channels\//, "");
    if (!slug || seen[slug] || slug === "search") continue;
    seen[slug] = 1;
    var chunk = parts[i + 1] ? parts[i + 1].slice(0, 1000) : "";
    var title = slug.replace(/-/g, " ");
    var tm = /(?:title|alt)="([^"]+)"/i.exec(chunk) || /class="[^"]*title[^"]*"[^>]*>([^<]+)/i.exec(chunk);
    if (tm) title = t(tm[1]);
    var cover = "";
    var cm =
      /(?:data-src|data-thumb|src)="(https?:\/\/[^"]+phncdn[^"]+)"/i.exec(chunk) ||
      /(?:data-src|src)="(https?:\/\/[^"]+\.(?:jpg|png|webp)[^"]*)"/i.exec(chunk);
    if (cm) cover = wrapCover(cm[1]);
    out.push({
      vod_id: "phch:" + slug,
      vod_name: "频道 · " + title,
      vod_pic: cover,
      vod_cover: cover,
      vod_remarks: "片商/频道",
    });
    if (out.length >= 40) break;
  }
  return out;
}

/** 分页解析：页内出现的最大 page=N（含列表与分页器链接） */
function maxPageFromHtml(html, page) {
  if (!html) return 0;
  var re = /[?&]page=(\d+)/g;
  var max = 0;
  var m;
  while ((m = re.exec(html))) max = Math.max(max, parseInt(m[1], 10) || 0);
  return max;
}

function estimateTotal(pagecount, listLength) {
  if (!pagecount || pagecount <= 1) return listLength;
  return (pagecount - 1) * PAGE_LIMIT + listLength;
}

/** categoryId → 列表 URL；非法回落热门 */
function categoryUrl(categoryId, page) {
  var id = t(categoryId) || "ht";
  if (SORTS.some(function (s) { return s.type_id === id; })) {
    return HOST + "/video?o=" + id + "&page=" + page;
  }
  var cm = id.match(/^c(\d+)$/);
  if (cm) return HOST + "/video?c=" + cm[1] + "&page=" + page;
  if (id.indexOf("path:") === 0) {
    var path = id.slice(5);
    return absUrl(path) + (path.indexOf("?") >= 0 ? "&" : "?") + "page=" + page;
  }
  return HOST + "/video?o=ht&page=" + page;
}

// ==================== flashvars 播放解析 ====================

/** 播放页 var flashvars_XXX = {...} JSON */
function parseFlashvars(html) {
  var m = String(html || "").match(/var\s+flashvars_\d+\s*=\s*(\{[\s\S]*?\});/);
  if (!m) return null;
  try {
    return JSON.parse(m[1]);
  } catch (e) {
    return null;
  }
}

/** mediaDefinitions → 按清晰度倒序的 HLS 源列表 */
function buildSourcesFromFlashvars(flashvars) {
  var sources = [];
  var defs = (flashvars && flashvars.mediaDefinitions) || [];
  for (var i = 0; i < defs.length; i++) {
    var def = defs[i];
    if (!def || !def.videoUrl) continue;
    var format = String(def.format || "").toLowerCase();
    var url = def.videoUrl;
    if (format !== "hls" && url.indexOf(".m3u8") < 0) continue;
    var quality = def.quality;
    if (Array.isArray(quality)) {
      quality = Math.max.apply(null, quality.map(Number)) || 0;
    } else {
      quality = parseInt(quality, 10) || 0;
    }
    sources.push({ quality: quality, url: url });
  }
  sources.sort(function (a, b) {
    return (b.quality || 0) - (a.quality || 0);
  });
  return sources;
}

// ==================== 5 个标准 handler ====================

/**
 * 作用：首页 = 4 排序源 + 36 分类 + 热门第一页推荐。
 * 出参：@returns {Promise<{class, list}>}
 */
async function home(params, context) {
  try {
    var from = (context && context.from) || "web";
    await log("info", `[home] from=${from}`);
    var html = await fetchHtml(categoryUrl("ht", 1));
    var list = parseVideoList(html);
    if (html && !list.length) {
      await log("warn", `[home] 页面非空但未解析到视频 len=${html.length} head=${html.slice(0, 120).replace(/\s+/g, " ")}`);
    }
    await log("info", `[home] class=${SORTS.length + CATEGORIES.length} list=${list.length}`);
    return { class: SORTS.concat(CATEGORIES), list: list };
  } catch (e) {
    await log("error", `[home] 失败: ${(e && e.message) || e}`);
    return { class: SORTS.concat(CATEGORIES), list: [] };
  }
}

/**
 * 作用：统一分类列表。categoryId 支持 ht/mr/mv/tr、c+数字、path: 整路径。
 * 入参：@param {Object} params - { categoryId, page }
 * 出参：@returns {Promise<{page, pagecount, total, list}>}
 */
async function category(params, context) {
  try {
    var categoryId = t((params && params.categoryId) || "") || "ht";
    var page = Math.max(1, parseInt((params && params.page) || 1, 10) || 1);
    var url = categoryUrl(categoryId, page);
    await log("info", `[category] categoryId=${categoryId}, page=${page}, url=${url}`);
    var html = await fetchHtml(url);
    var list = parseVideoList(html);
    if (!html) {
      await log("warn", `[category] 第 ${page} 页无响应（已到末页或网络失败）`);
      return { page: page, pagecount: 0, total: 0, list: [] };
    }
    if (!list.length) {
      await log("warn", `[category] 页面非空但未解析到视频 len=${html.length} head=${html.slice(0, 120).replace(/\s+/g, " ")}`);
    }
    var pagecount = maxPageFromHtml(html) || (list.length ? page + 1 : page);
    await log("info", `[category] count=${list.length} pagecount=${pagecount}`);
    return { page: page, pagecount: pagecount, total: estimateTotal(pagecount, list.length), list: list };
  } catch (e) {
    await log("error", `[category] 失败: ${(e && e.message) || e}`);
    return { page: 1, pagecount: 0, total: 0, list: [] };
  }
}

/**
 * 作用：搜索。类型（video/pornstar/channel）与视频排序由 PH_SEARCH_TYPE / PH_SEARCH_SORT 控制。
 * 入参：@param {Object} params - { keyword/wd, page }
 * 出参：@returns {Promise<{page, pagecount, total, list}>}
 */
async function search(params, context) {
  try {
    var keyword = t((params && (params.keyword || params.wd || params.q)) || "");
    var page = Math.max(1, parseInt((params && params.page) || 1, 10) || 1);
    if (!keyword) return { page: 1, pagecount: 0, total: 0, list: [] };

    var stype = SEARCH_TYPE;
    var sort = SEARCH_SORT;
    var list = [];
    var searchHtml = "";
    await log("info", `[search] keyword=${keyword}, page=${page}, stype=${stype}, sort=${sort}`);

    if (stype === "pornstar") {
      searchHtml = await fetchHtml(HOST + "/pornstars?search=" + encodeURIComponent(keyword) + (page > 1 ? "&page=" + page : ""));
      list = parsePornstarList(searchHtml);
      if (!list.length) {
        // 回退另一路径
        searchHtml = await fetchHtml(HOST + "/pornstar/search?search=" + encodeURIComponent(keyword));
        list = parsePornstarList(searchHtml);
      }
    } else if (stype === "channel") {
      searchHtml = await fetchHtml(HOST + "/channels/search?search=" + encodeURIComponent(keyword) + (page > 1 ? "&page=" + page : ""));
      list = parseChannelList(searchHtml);
    } else {
      var vurl = HOST + "/video/search?search=" + encodeURIComponent(keyword) + "&page=" + page;
      if (sort) vurl += "&o=" + sort;
      searchHtml = await fetchHtml(vurl);
      list = parseVideoList(searchHtml);
    }

    await log("info", `[search] count=${list.length}`);
    if (!list.length) return { page: page, pagecount: 0, total: 0, list: list };
    var pagecount = maxPageFromHtml(searchHtml) || (stype === "video" && list.length ? page + 1 : 1);
    return { page: page, pagecount: pagecount, total: estimateTotal(pagecount, list.length), list: list };
  } catch (e) {
    await log("error", `[search] 失败: ${(e && e.message) || e}`);
    return { page: 1, pagecount: 0, total: 0, list: [] };
  }
}

/**
 * 作用：详情。
 *   - viewkey：flashvars 解析多清晰度 → 每个清晰度一条线路（线路名即 play 时的 flag）
 *   - phstar:/phch:：女优/频道主页 → 本页视频转剧集列表
 * 入参：@param {Object} params - { videoId }
 * 出参：@returns {Promise<{list}>}
 */
async function detail(params, context) {
  try {
    var videoId = t((params && (params.videoId || params.id)) || "");
    if (!videoId) return { list: [] };
    await log("info", `[detail] videoId=${videoId}`);

    // 女优主页 → 视频剧集
    if (videoId.indexOf("phstar:") === 0 || videoId.indexOf("phch:") === 0) {
      var isStar = videoId.indexOf("phstar:") === 0;
      var slug = videoId.slice(isStar ? 7 : 5);
      var pageUrl = isStar ? HOST + "/pornstar/" + encodeURIComponent(slug) : HOST + "/channels/" + encodeURIComponent(slug);
      var html = await fetchHtml(pageUrl);
      var videos = parseVideoList(html);
      var title = slug.replace(/-/g, " ");
      var tm = /<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(html || "");
      if (tm) title = t(tm[1].replace(/<[^>]+>/g, "")) || title;
      var display = (isStar ? "女优 · " : "频道 · ") + title;
      var episodes = videos.map(function (v) {
        return { name: t(v.vod_name).slice(0, 40), playId: v.vod_id };
      });
      await log("info", `[detail] ${videoId} name=${display} episodes=${episodes.length}`);
      return {
        list: [
          {
            vod_id: videoId,
            vod_name: display,
            vod_pic: videos[0] ? videos[0].vod_pic : "",
            vod_cover: videos[0] ? videos[0].vod_pic : "",
            vod_remarks: "本页 " + episodes.length + " 部",
            vod_content: "共 " + episodes.length + " 部（本页）",
            vod_play_from: isStar ? "女优视频" : "频道视频",
            vod_play_url: episodes.map(function (e) { return e.name + "$" + e.playId; }).join("#"),
            vod_play_sources: [{ name: isStar ? "女优视频" : "频道视频", episodes: episodes }],
          },
        ],
      };
    }

    // 视频详情：viewkey → flashvars
    var viewkey = videoId;
    if (viewkey.indexOf("viewkey=") >= 0) viewkey = extractViewkey(viewkey) || viewkey;
    var vUrl = HOST + "/view_video.php?viewkey=" + encodeURIComponent(viewkey);
    var vHtml = await fetchHtml(vUrl);
    var flashvars = parseFlashvars(vHtml);
    if (!flashvars) {
      await log("warn", `[detail] 未能解析播放数据 viewkey=${viewkey}`);
      return {
        list: [
          {
            vod_id: viewkey,
            vod_name: viewkey,
            vod_content: "未能解析播放数据",
            vod_play_sources: [],
          },
        ],
      };
    }

    var sources = buildSourcesFromFlashvars(flashvars);
    var cover = wrapCover(flashvars.image_url || "");
    var h1m = /<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(vHtml || "");
    var ogm = /<meta[^>]*og:title[^>]*content="([^"]+)"/i.exec(vHtml || "");
    var pageTitle = t(
      flashvars.video_title ||
        (h1m ? h1m[1].replace(/<[^>]+>/g, "") : "") ||
        (ogm ? ogm[1] : "") ||
        viewkey
    );
    var duration = parseInt(flashvars.video_duration || 0, 10) || 0;
    var durationText = duration ? Math.floor(duration / 60) + ":" + String(duration % 60).padStart(2, "0") : "";

    // 每个清晰度一条线路：play 时用 flag（线路名）选流
    var playSources = sources.map(function (s) {
      return { name: (s.quality || "未知") + "p", episodes: [{ name: "正片", playId: viewkey }] };
    });
    await log("info", `[detail] ${viewkey} name=${pageTitle} sources=${playSources.map(function (s) { return s.name; }).join("/")}`);
    return {
      list: [
        {
          vod_id: viewkey,
          vod_name: pageTitle,
          vod_pic: cover,
          vod_cover: cover,
          vod_remarks: durationText ? "时长 " + durationText : "",
          vod_content: durationText ? "时长 " + durationText : "",
          vod_play_from: playSources.map(function (s) { return s.name; }).join("$$$"),
          vod_play_url: playSources.map(function () { return "正片$" + viewkey; }).join("$$$"),
          vod_play_sources: playSources,
        },
      ],
    };
  } catch (e) {
    await log("error", `[detail] 失败: ${(e && e.message) || e}`);
    return { list: [] };
  }
}

/**
 * 作用：播放。playId 为 viewkey；flag 为线路名（如 "720p"），按清晰度选流。
 *   未命中线路名时取最高清晰度；解析失败回退网页嗅探（parse=1）。
 * 入参：@param {Object} params - { playId, flag }
 * 出参：@returns {Promise<{urls, flag, header, parse}>}
 */
async function play(params, context) {
  var flag = t((params && params.flag) || "") || "在线";
  var playId = t((params && (params.playId || params.url || params.id)) || "");
  if (!playId || playId.indexOf("phstar:") === 0 || playId.indexOf("phch:") === 0) {
    await log("error", `[play] playId 无效: ${playId}`);
    return { urls: [], flag: flag, header: {}, parse: 0 };
  }
  if (playId.indexOf("viewkey=") >= 0) playId = extractViewkey(playId) || playId;

  try {
    var pageUrl = HOST + "/view_video.php?viewkey=" + encodeURIComponent(playId);
    await log("info", `[play] playId=${playId}, flag=${flag}`);
    var html = await fetchHtml(pageUrl);
    var flashvars = parseFlashvars(html);
    var sources = flashvars ? buildSourcesFromFlashvars(flashvars) : [];

    if (sources.length) {
      // flag 形如 "720p"：命中选它，未命中取最高清
      var want = parseInt(flag, 10) || 0;
      var picked = sources.find(function (s) { return s.quality === want; }) || sources[0];
      await log("info", `[play] parse=0 quality=${picked.quality}p url=${picked.url.slice(0, 100)}`);
      return {
        urls: [{ name: (picked.quality || "未知") + "p", url: picked.url }],
        flag: flag,
        header: { "User-Agent": UA, Referer: pageUrl, Origin: HOST },
        parse: 0,
      };
    }

    await log("warn", `[play] 未解出直链，回退嗅探 parse=1 url=${pageUrl}`);
    return {
      urls: [{ name: "播放页", url: pageUrl }],
      flag: flag,
      header: { "User-Agent": UA, Referer: pageUrl, Origin: HOST },
      parse: 1,
    };
  } catch (e) {
    await log("error", `[play] 失败: ${(e && e.message) || e}`);
    return {
      urls: [{ name: "播放页", url: HOST + "/view_video.php?viewkey=" + encodeURIComponent(playId) }],
      flag: flag,
      header: { "User-Agent": UA, Referer: HOST + "/", Origin: HOST },
      parse: 1,
    };
  }
}
