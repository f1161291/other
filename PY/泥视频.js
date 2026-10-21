// @name 泥视频
// @author 梦
// @description 影视站：https://www.nivod.cc/ ，支持首页、分类、详情、搜索与播放
// @dependencies cheerio
// @version 1.0.4
// @downloadURL https://gh-proxy.org/https://github.com/Silent1566/OmniBox-Spider/raw/refs/heads/main/影视/采集/泥视频.js

const OmniBox = require("omnibox_sdk");
const runner = require("spider_runner");
const cheerio = require("cheerio");

const BASE_URL = (process.env.NIVOD_HOST || "https://www.nivod.cc").replace(/\/$/, "");
const UA = process.env.NIVOD_UA || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36";
const HOME_CACHE_TTL = Number(process.env.NIVOD_HOME_CACHE_TTL || 900);
const CATEGORY_CACHE_TTL = Number(process.env.NIVOD_CATEGORY_CACHE_TTL || 900);
const DETAIL_CACHE_TTL = Number(process.env.NIVOD_DETAIL_CACHE_TTL || 1800);
const SEARCH_CACHE_TTL = Number(process.env.NIVOD_SEARCH_CACHE_TTL || 600);
const PLAY_CACHE_TTL = Number(process.env.NIVOD_PLAY_CACHE_TTL || 300);
const VERIFY_CACHE_TTL = Number(process.env.NIVOD_VERIFY_CACHE_TTL || 600);

const CHANNELS = [
  { id: "movie", name: "电影" },
  { id: "tv", name: "电视剧" },
  { id: "show", name: "综艺" },
  { id: "anime", name: "动漫" },
  { id: "doc", name: "纪录" },
];
const CHANNEL_IDS = new Set(CHANNELS.map((item) => item.id));
const CLASS_LIST = CHANNELS.map((item) => ({ type_id: item.id, type_name: item.name }));
const FILTERS = {};

async function home() {
  try {
    const html = await getCachedText("nivod:home", HOME_CACHE_TTL, async () => (await requestText(`${BASE_URL}/`)).body);
    const $ = cheerio.load(html);
    const list = [];
    $("div.qy-mod-header").each((_, el) => {
      const items = parseCards($, $(el).parent().find("ul.qy-mod-ul").first());
      list.push(...items);
    });
    const finalList = dedupeVodList(list.length ? list : parseCards($, $.root())).slice(0, 40);
    await OmniBox.log("info", `[泥视频][home] count=${finalList.length}`);
    return { class: CLASS_LIST, filters: FILTERS, list: finalList };
  } catch (e) {
    await OmniBox.log("error", `[泥视频][home] failed: ${e.message || e}`);
    return { class: CLASS_LIST, filters: FILTERS, list: [] };
  }
}

async function category(params = {}) {
  try {
    const tid = String(params.type_id || params.categoryId || params.tid || "movie");
    const page = Math.max(1, Number(params.page || params.pg || 1));
    const channel = CHANNEL_IDS.has(tid) ? tid : "movie";
    if (page > 1) {
      await OmniBox.log("info", `[泥视频][category] tid=${channel} page=${page} no pagination, empty`);
      return { page, pagecount: 1, limit: 0, total: 0, filters: FILTERS[channel] || [], list: [] };
    }
    const url = `${BASE_URL}/class.html?channel=${encodeURIComponent(channel)}`;
    let list = [];
    try {
      const html = await getCachedText(`nivod:category:${channel}`, CATEGORY_CACHE_TTL, async () => (await requestText(url)).body);
      const $ = cheerio.load(html);
      list = parseCards($, $.root());
    } catch (e) {
      await OmniBox.log("warn", `[泥视频][category] 分类页不可用(${e.message || e})，回退首页分区`);
      const homeHtml = await getCachedText("nivod:home", HOME_CACHE_TTL, async () => (await requestText(`${BASE_URL}/`)).body);
      list = parseHomeSection(cheerio.load(homeHtml), channel);
    }
    list = dedupeVodList(list);
    await OmniBox.log("info", `[泥视频][category] tid=${channel} count=${list.length}`);
    return { page, pagecount: 1, limit: list.length, total: list.length, filters: FILTERS[channel] || [], list };
  } catch (e) {
    await OmniBox.log("error", `[泥视频][category] failed: ${e.message || e}`);
    return { page: 1, pagecount: 1, limit: 0, total: 0, filters: [], list: [] };
  }
}

async function detail(params = {}) {
  try {
    const vodId = absUrl(params.vod_id || params.videoId || params.id || "");
    if (!vodId || !/\/voddetail\//.test(vodId)) return { list: [] };
    const html = await getCachedText(`nivod:detail:${vodId}`, DETAIL_CACHE_TTL, async () => (await requestText(vodId)).body);
    const vod = parseDetail(html, vodId);
    const episodes = vod.vod_play_sources?.[0]?.episodes || [];
    const numericId = String(vodId).match(/\/voddetail\/(\d+)/)?.[1] || "";
    if (numericId && episodes.length) {
      try {
        await OmniBox.setCache(`nivod:epmap:${numericId}`, JSON.stringify(Object.fromEntries(episodes.map((item) => [item.playId, item.name]))), DETAIL_CACHE_TTL);
      } catch (_) {}
    }
    await OmniBox.log("info", `[泥视频][detail] vod=${vod.vod_name || vodId} eps=${episodes.length}`);
    return { list: [vod] };
  } catch (e) {
    await OmniBox.log("error", `[泥视频][detail] failed: ${e.message || e}`);
    return { list: [] };
  }
}

async function search(params = {}) {
  try {
    const wd = String(params.wd || params.keyword || "").trim();
    const page = Math.max(1, Number(params.page || 1));
    if (!wd) return { page, pagecount: 1, limit: 0, total: 0, list: [] };
    if (page > 1) return { page, pagecount: 1, limit: 0, total: 0, list: [] };
    const url = `${BASE_URL}/search.html?keyword=${encodeURIComponent(wd)}`;
    const html = await getCachedText(`nivod:search:${wd}`, SEARCH_CACHE_TTL, async () => (await requestText(url, { referer: `${BASE_URL}/` })).body);
    const $ = cheerio.load(html);
    const list = dedupeVodList(parseCards($, $.root()));
    await OmniBox.log("info", `[泥视频][search] wd=${wd} count=${list.length}`);
    return { page, pagecount: 1, limit: list.length, total: list.length, list };
  } catch (e) {
    await OmniBox.log("error", `[泥视频][search] failed: ${e.message || e}`);
    return { page: 1, pagecount: 1, limit: 0, total: 0, list: [] };
  }
}

async function play(params = {}) {
  try {
    const flag = String(params.flag || params.from || "官方线路");
    const playId = String(params.playId || params.id || "").trim();
    await OmniBox.log("info", `[泥视频][play] enter playId=${playId} flag=${flag}`);
    if (!playId) return normalizePlayResult({ parse: 0, url: "", urls: [], header: {} }, params);

    if (/\.(m3u8|mp4)(\?|#|$)/i.test(playId)) {
      const url = resolvePlayUrl(playId);
      return normalizePlayResult({ parse: 0, flag, url, urls: [{ name: "播放", url }], header: {} }, params);
    }

    const wantedName = await lookupEpisodeName(playId) || String(params.episodeName || params.name || "");
    const cacheKey = `nivod:play:v2:${playId}:${normPlayName(wantedName)}`;
    let parsed = null;
    try {
      const cached = await OmniBox.getCache(cacheKey);
      if (cached) parsed = JSON.parse(String(cached));
    } catch (_) {}

    if (!parsed?.url) {
      parsed = await resolvePlayInfo(playId, wantedName);
      if (parsed?.url) {
        try {
          await OmniBox.setCache(cacheKey, JSON.stringify({ url: parsed.url, flag: parsed.flag || flag }), PLAY_CACHE_TTL);
        } catch (_) {}
      } else {
        await OmniBox.log("warn", `[泥视频][play] 未解析到播放地址，不写缓存 playId=${playId}`);
      }
    }

    if (parsed?.url) {
      const url = await pickPlayableUrl(parsed.url, parsed.alts || []);
      const header = { Referer: parsed.referer || `${BASE_URL}/`, Origin: BASE_URL, "User-Agent": UA };
      await OmniBox.log("info", `[泥视频][play] resolved flag=${parsed.flag || flag} url=${url}`);
      return normalizePlayResult({ parse: 0, flag: parsed.flag || flag, url, urls: [{ name: "播放", url }], header }, params);
    }

    const playPage = absUrl(playId);
    const sniffHeaders = { "User-Agent": UA, Referer: playPage, Origin: BASE_URL };
    const sniffed = await trySniffVideo(playPage, sniffHeaders);
    if (sniffed) return normalizePlayResult(sniffed, params);

    await OmniBox.log("warn", `[泥视频][play] final fallback parse=1 url=${playPage}`);
    return normalizePlayResult({ parse: 1, flag, url: playPage, urls: [{ name: "播放", url: playPage }], header: sniffHeaders }, params);
  } catch (e) {
    await OmniBox.log("error", `[泥视频][play] failed: ${e.message || e}`);
    return normalizePlayResult({ parse: 0, url: "", urls: [], header: {} }, params);
  }
}

function normalizePlayResult(result, params = {}) {
  const fallbackFlag = String(params.flag || params.from || "官方线路");
  const out = result && typeof result === "object" && !Array.isArray(result) ? { ...result } : {};
  const rawUrls = Array.isArray(out.urls) ? out.urls : [];
  const urls = rawUrls
    .map((item) => (item && typeof item === "object"
      ? { name: String(item.name || "播放"), url: String(item.url || "") }
      : { name: "播放", url: String(item || "") }))
    .filter((item) => item.url);
  let header = out.header;
  if (typeof header === "string") {
    try {
      header = JSON.parse(header);
    } catch (_) {
      header = {};
    }
  }
  if (!header || typeof header !== "object" || Array.isArray(header)) header = {};
  const url = String(out.url || (urls[0] && urls[0].url) || "");
  const parse = Number(out.parse);
  return {
    ...out,
    parse: Number.isFinite(parse) ? parse : 0,
    flag: String(out.flag || fallbackFlag),
    url,
    urls: urls.length ? urls : (url ? [{ name: "播放", url }] : []),
    header,
  };
}

function normPlayName(value) {
  return String(value == null ? "" : value)
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/(\d+)/g, (digit) => String(Number(digit)));
}

function pickPlayGroup(pdatas = [], wantedName = "") {
  const list = Array.isArray(pdatas) ? pdatas.filter((item) => item && item.playurl) : [];
  if (!list.length) return [];
  const wanted = normPlayName(wantedName);
  if (!wanted) return list;
  const exact = list.filter((item) => normPlayName(item.name) === wanted);
  if (exact.length) return exact;
  const loose = list.filter((item) => {
    const name = normPlayName(item.name);
    return name.includes(wanted) || wanted.includes(name);
  });
  if (loose.length) return loose;
  return list;
}

async function lookupEpisodeName(playId) {
  const m = String(playId || "").match(/\/vodplay\/(\d+)/);
  if (!m) return "";
  try {
    const cached = await OmniBox.getCache(`nivod:epmap:${m[1]}`);
    if (!cached) return "";
    const map = JSON.parse(String(cached));
    return String(map?.[String(playId)] || "");
  } catch (_) {
    return "";
  }
}

async function resolvePlayInfo(playId, wantedName = "") {
  const raw = String(playId);
  const playPath = raw.match(/\/vodplay\//) ? raw : "";
  const playPage = absUrl(playPath || raw);
  const keys = [];
  const m = raw.match(/\/vodplay\/(\d+)\/([^#?]+)/);
  if (m) keys.push(`${m[1]}-${m[2]}`, m[1]);
  const legacy = raw.match(/(\d+)-ep(\d+)/);
  if (legacy) keys.push(`${legacy[1]}-ep${legacy[2]}`);
  for (const key of keys) {
    const xhrUrl = `${BASE_URL}/xhr_playinfo/${key}`;
    try {
      const res = await requestText(xhrUrl, { referer: playPage || `${BASE_URL}/`, expect: "json" });
      const data = JSON.parse(res.body);
      const pdatas = Array.isArray(data?.pdatas) ? data.pdatas : [];
      const group = pickPlayGroup(pdatas, wantedName);
      const urls = group
        .map((item) => String(item?.playurl || "").trim())
        .filter((url) => /\.(m3u8|mp4)(\?|#|$)/i.test(url));
      if (urls.length) {
        await OmniBox.log("info", `[泥视频][play] key=${key} want=${wantedName || "-"} group=${JSON.stringify(group.map((x) => x?.name))} lines=${urls.length} first=${urls[0].slice(0, 80)}`);
        return { url: urls[0], alts: urls.slice(1, 3), referer: playPage || `${BASE_URL}/` };
      }
      await OmniBox.log("warn", `[泥视频][play] playinfo 无有效线路 ${xhrUrl}`);
    } catch (e) {
      await OmniBox.log("warn", `[泥视频][play] playinfo 请求失败 key=${key}: ${e.message || e}`);
    }
  }
  if (raw.includes("detail/")) {
    try {
      const html = (await requestText(playId)).body;
      const vod = parseDetail(html, playId);
      const first = vod?.vod_play_sources?.[0]?.episodes?.[0]?.playId || "";
      if (first) return resolvePlayInfo(first);
    } catch (e) {
      await OmniBox.log("warn", `[泥视频][play] detail 回退失败: ${e.message || e}`);
    }
  }
  return { url: "", alts: [], flag: "", referer: playPage };
}

async function pickPlayableUrl(primary, alts = []) {
  const candidates = [primary, ...alts].filter((item) => /\.m3u8(\?|#|$)/i.test(item)).slice(0, 3);
  if (!candidates.length) return String(primary || "");
  for (const candidate of candidates) {
    try {
      const verified = await OmniBox.getCache(`nivod:verified:${candidate}`);
      if (verified) {
        await OmniBox.log("info", `[泥视频][play] 直链近期已验证，跳过探测 host=${hostOf(candidate)}`);
        return candidate;
      }
    } catch (_) {}
  }
  const results = await Promise.all(candidates.map(async (url) => ({ url, probe: await probeStream(url) })));
  const hit = results.find((item) => item.probe?.ok);
  if (hit) {
    const effective = hit.probe.url || hit.url;
    try {
      await OmniBox.setCache(`nivod:verified:${effective}`, "1", VERIFY_CACHE_TTL);
    } catch (_) {}
    await OmniBox.log("info", `[泥视频][play] 可播线路 host=${hostOf(effective)}`);
    return effective;
  }
  await OmniBox.log("warn", `[泥视频][play] 所有线路探测未通过，返回首个直链 host=${hostOf(candidates[0])}`);
  return candidates[0];
}

async function probeStream(streamUrl) {
  const toText = (value) => (typeof value === "string" ? value : Buffer.isBuffer(value) ? value.toString() : String(value || ""));
  const get = (u, extra) => OmniBox.request(u, {
    method: "GET",
    headers: {
      "User-Agent": UA,
      Referer: `${BASE_URL}/`,
      "Accept-Encoding": "identity",
      ...(extra || {}),
    },
    timeout: 10000,
  });
  const follow = async (u, extra) => {
    let current = u;
    for (let hop = 0; hop < 4; hop += 1) {
      const res = await get(current, extra);
      const status = Number(res?.statusCode || 0);
      const location = res?.headers?.location || res?.headers?.Location || "";
      if (status >= 300 && status < 400 && location) {
        current = absJoin(current, location);
        continue;
      }
      return { status, body: res?.body, url: current };
    }
    return { status: 0, body: "", url: current };
  };
  try {
    let got = await follow(streamUrl);
    if (got.status < 200 || got.status >= 300 || !/#EXTM3U/i.test(toText(got.body))) {
      await OmniBox.log("warn", `[泥视频][play] 清单不可用 status=${got.status} len=${toText(got.body).length} host=${hostOf(got.url)}`);
      return { ok: false, url: got.url };
    }
    let base = got.url;
    let text = toText(got.body);
    let media = firstPlaylistUri(text, base);
    if (/#EXT-X-STREAM-INF/i.test(text) && media) {
      got = await follow(media);
      if (got.status < 200 || got.status >= 300 || !/#EXTM3U/i.test(toText(got.body))) return { ok: false, url: got.url };
      base = got.url;
      text = toText(got.body);
      media = firstPlaylistUri(text, base);
    }
    if (!media) return { ok: true, url: base };
    const seg = await follow(media, { Range: "bytes=0-4095" });
    const segLen = Buffer.isBuffer(seg.body) ? seg.body.length : Buffer.byteLength(String(seg.body || ""));
    const ok = (seg.status === 200 || seg.status === 206) && segLen > 400;
    await OmniBox.log(ok ? "info" : "warn", `[泥视频][play] 分片探测 status=${seg.status} len=${segLen} ok=${ok} host=${hostOf(base)}`);
    return { ok, url: base };
  } catch (e) {
    await OmniBox.log("warn", `[泥视频][play] 流探测失败: ${e.message || e}`);
    return { ok: false, url: streamUrl };
  }
}

async function trySniffVideo(sniffUrl, headers = {}) {
  if (!sniffUrl || typeof OmniBox.sniffVideo !== "function") return null;
  try {
    await OmniBox.log("info", `[泥视频][play] sniffVideo start url=${sniffUrl}`);
    const sniffed = await OmniBox.sniffVideo(sniffUrl, headers);
    if (sniffed?.url) {
      return { parse: 0, flag: String(sniffed.flag || "嗅探线路"), url: sniffed.url, urls: [{ name: "播放", url: sniffed.url }], header: sniffed.header || headers };
    }
  } catch (e) {
    await OmniBox.log("warn", `[泥视频][play] sniffVideo failed: ${e.message || e}`);
  }
  return null;
}

function parseHomeSection($, channel) {
  const items = [];
  $("div.qy-mod-header").each((_, el) => {
    const link = $(el).find("a[href*='class.html']").first();
    const href = String(link.attr("href") || "");
    if (href && !href.includes(`channel=${channel}`)) return;
    items.push(...parseCards($, $(el).parent().find("ul.qy-mod-ul").first()));
  });
  return items;
}

function parseCards($, root) {
  const list = [];
  $(root).find("li.qy-mod-li, ul.qy-mod-ul li").each((_, el) => {
    const node = $(el);
    const link = node.find("a.qy-mod-link, a[href*='/voddetail/']").first();
    const href = String(link.attr("href") || "").trim();
    const m = href.match(/\/voddetail\/(\d+)/);
    if (!m) return;
    const img = node.find("img").first();
    const name = cleanText(img.attr("alt") || node.find(".title-wrap a").first().attr("title") || node.find(".title-wrap span").first().text())
      || cleanText(node.find(".title-wrap").first().text());
    const pic = String(img.attr("data-original") || img.attr("data-src") || img.attr("src") || "")
      || String(node.find("[style*='background-image']").first().attr("style") || "").match(/url\(["']?([^"')]+)/)?.[1] || "";
    const remarks = cleanText(node.find(".qy-mod-label").first().text());
    if (!name) return;
    list.push({
      vod_id: `${BASE_URL}/voddetail/${m[1]}`,
      vod_name: name,
      vod_pic: absUrl(pic || `/imgs/${m[1]}.jpg`),
      vod_remarks: remarks,
    });
  });
  return list;
}

function parseDetail(html, detailUrl) {
  const $ = cheerio.load(html);
  const idMatch = String(detailUrl).match(/\/voddetail\/(\d+)/);
  const vodId = idMatch ? idMatch[1] : "";
  const titleRaw = String($("title").first().text() || "").split("_")[0];
  const name = cleanText($(".right-title").first().text()) || cleanText(titleRaw);
  const desc = cleanText($('meta[name="description"]').attr("content") || "");
  const episodes = parseEpisodes($, vodId);
  const vod = {
    vod_id: detailUrl,
    vod_name: name,
    vod_pic: vodId ? `${BASE_URL}/imgs/${vodId}.jpg` : "",
    vod_remarks: cleanText($("#updateTxt").first().text()),
    vod_year: cleanText($("#postYear").first().text()),
    vod_area: cleanText($("#region").first().text()),
    vod_lang: cleanText($("#langName").first().text()),
    vod_director: cleanText($("#director").first().text()),
    vod_actor: cleanText($("#actors").first().text()),
    vod_type: cleanText($("#types-label").first().text()),
    vod_remark: cleanText($(".score-label").first().text()),
    vod_content: desc,
    type_name: cleanText($("#types-label").first().text()),
    play_from: episodes.length ? "官方线路" : "",
    play_note: cleanText($("#updateTxt").first().text()),
    vod_play_from: episodes.length ? "官方线路" : "",
    vod_play_url: episodes.map((item) => `${item.name}$${item.playId}`).join("#"),
    vod_play_sources: episodes.length ? [{ name: "官方线路", episodes: episodes.map(({ name: epName, playId }) => ({ name: epName, playId })) }] : [],
  };
  return dedupeEpisodesInVod(vod);
}

function parseEpisodes($, vodId = "") {
  const items = [];
  const seen = new Set();
  $("a[href*='/vodplay/']").each((_, el) => {
    const href = String($(el).attr("href") || "").trim();
    if (!href || seen.has(href)) return;
    const m = href.match(/\/vodplay\/(\d+)\/([^#?]+)/);
    if (!m || (vodId && m[1] !== vodId)) return;
    seen.add(href);
    let label = cleanText($(el).find(".item").first().text()) || cleanText($(el).find(".btn-label").first().text());
    if (label === "播放") label = "";
    const seg = m[2];
    const epm = seg.match(/^ep(\d+)$/i);
    if (epm) {
      const ep = Number(epm[1]);
      items.push({ name: label || `第${String(ep).padStart(2, "0")}集`, playId: href, ep });
      return;
    }
    items.push({ name: label || (seg === "v" ? "正片" : seg), playId: href, ep: null });
  });
  items.sort((a, b) => {
    if (a.ep == null && b.ep == null) return 0;
    if (a.ep == null) return -1;
    if (b.ep == null) return 1;
    return a.ep - b.ep;
  });
  return items;
}

function dedupeEpisodesInVod(vod) {
  const sources = vod.vod_play_sources || [];
  vod.vod_play_sources = sources.map((source) => ({
    ...source,
    episodes: (source.episodes || []).filter((item, index, arr) => arr.findIndex((x) => x.playId === item.playId) === index),
  }));
  return vod;
}

function dedupeVodList(list = []) {
  const seen = new Set();
  return list.filter((item) => {
    const key = item?.vod_id || item?.vod_name || "";
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function cleanText(value) {
  return String(value == null ? "" : value)
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function absUrl(raw = "") {
  const value = String(raw || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  return `${BASE_URL}${value.startsWith("/") ? "" : "/"}${value}`;
}

function resolvePlayUrl(rawUrl = "") {
  const value = String(rawUrl || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  return absUrl(value);
}

function absJoin(base = "", rel = "") {
  try {
    return new URL(String(rel), String(base)).toString();
  } catch (_) {
    return String(rel || base);
  }
}

function hostOf(url = "") {
  try {
    return new URL(String(url)).host;
  } catch (_) {
    return String(url || "").split("/")[2] || "";
  }
}

function firstPlaylistUri(playlist = "", baseUrl = "") {
  const lines = String(playlist || "").split(/\r?\n/);
  for (const raw of lines) {
    const line = String(raw || "").trim();
    if (!line || line.startsWith("#")) continue;
    return absJoin(baseUrl, line);
  }
  return "";
}

async function getCachedText(cacheKey, ttl, producer) {
  try {
    const cached = await OmniBox.getCache(cacheKey);
    if (cached) return String(cached);
  } catch (_) {}
  const value = await producer();
  if (value) {
    try {
      await OmniBox.setCache(cacheKey, value, ttl);
    } catch (_) {}
  }
  return value;
}

async function requestText(url, options = {}) {
  const referer = options.referer || `${BASE_URL}/`;
  const expect = options.expect || "";
  const maxRedirects = 3;
  let current = url;
  for (let hop = 0; hop <= maxRedirects; hop += 1) {
    let res;
    try {
      res = await OmniBox.request(current, {
        method: "GET",
        headers: {
          "User-Agent": UA,
          Referer: referer,
          Accept: expect === "json" ? "application/json, text/plain, */*" : "text/html,application/xhtml+xml,*/*;q=0.8",
          "Accept-Encoding": "identity",
        },
        timeout: 15000,
      });
    } catch (e) {
      throw new Error(`network ${String(e.message || e).slice(0, 80)} url=${current}`);
    }
    const status = Number(res?.statusCode || 0);
    const location = res?.headers?.location || res?.headers?.Location || "";
    if (status >= 300 && status < 400 && location) {
      current = absJoin(current, location);
      continue;
    }
    if (status === 404) throw new Error(`HTTP 404 url=${current}`);
    if (status === 403) throw new Error(`HTTP 403 url=${current}`);
    if (status !== 200 && status !== 206) throw new Error(`HTTP ${status} url=${current}`);
    const body = bodyToText(res.body);
    if (!body) throw new Error(`empty body status=${status} url=${current}`);
    await OmniBox.log("info", `[泥视频][request] GET ${current} -> ${status} len=${body.length}`);
    return { body, url: current, status };
  }
  throw new Error(`too many redirects url=${url}`);
}

function bodyToText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof Buffer !== "undefined" && Buffer.isBuffer(value)) {
    if (value.length >= 2 && value[0] === 0x1f && value[1] === 0x8b) {
      try {
        return require("zlib").gunzipSync(value).toString("utf8");
      } catch (_) {}
    }
    if (value.length >= 4 && value[0] === 0x78 && value[1] >= 0x01 && value[1] <= 0x5f) {
      try {
        return require("zlib").inflateSync(value).toString("utf8");
      } catch (_) {}
    }
    return value.toString("utf8");
  }
  try {
    return String(value);
  } catch (_) {
    return "";
  }
}

module.exports = { home, category, detail, search, play };
runner.run(module.exports);
