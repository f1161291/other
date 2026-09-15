// @name 黄豆短剧
// @author 梦
// @description API 站：https://xqjzvcvt.top，支持首页、分类、搜索、详情与播放解析
// @version 1.0.0
// @downloadURL 
// @dependencies crypto-js

const OmniBox = require("omnibox_sdk");
const runner = require("spider_runner");
const crypto = require("crypto");
const zlib = require("zlib");
const https = require("https");

const HOST = process.env.HUANGDOU_HOST || "https://xqjzvcvt.top";
const API = `${HOST}/api`;
const PLATFORM_KEY = process.env.HUANGDOU_PLATFORM_KEY || "7961beb44246e3012ce228d6b5ced05a";
const VERSION = "2.0.0";
const DEVICE_TYPE = "web";
const SESSION_ID = crypto.randomUUID().replace(/-/g, "");
const DEVICE_ID = SESSION_ID;
const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

module.exports = { home, category, detail, search, play };
runner.run(module.exports);

let classCache = null;
const filterCache = {};

function text(value) {
  return String(value == null ? "" : value).trim();
}

function cleanSid(value) {
  return text(value).replace(/^rp_/, "");
}

function getBodyBuffer(res) {
  const body = res && typeof res === "object" && "body" in res ? res.body : res;
  if (Buffer.isBuffer(body)) return body;
  if (body instanceof Uint8Array) return Buffer.from(body);
  if (typeof body === "string") return Buffer.from(body, "binary");
  return Buffer.alloc(0);
}

function getKey(rid) {
  const ridHex = rid.replace(/-/g, "");
  const ridBuf = Buffer.from(ridHex, "hex");
  return crypto.createHmac("sha256", Buffer.from(PLATFORM_KEY, "utf8")).update(ridBuf).digest();
}

function encryptBody(dataObj, rid) {
  const rawJson = JSON.stringify({
    token: "",
    deviceId: DEVICE_ID,
    data: dataObj || {},
  });
  const gzipped = zlib.gzipSync(Buffer.from(rawJson, "utf8"));
  const iv = crypto.randomBytes(16);
  const key = getKey(rid);

  const cipher = crypto.createCipheriv("aes-256-cbc", key, iv);
  const encrypted = Buffer.concat([cipher.update(gzipped), cipher.final()]);
  return Buffer.concat([iv, encrypted]);
}

function decryptResponse(blob, rid) {
  if (!blob || blob.length < 32 || (blob.length - 16) % 16 !== 0) {
    try {
      return JSON.parse(blob.toString("utf8"));
    } catch (_) {
      return {};
    }
  }
  try {
    const iv = blob.slice(0, 16);
    const ciphertext = blob.slice(16);
    const key = getKey(rid);

    const decipher = crypto.createDecipheriv("aes-256-cbc", key, iv);
    let plain = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    if (plain.length >= 2 && plain[0] === 0x1f && plain[1] === 0x8b) {
      plain = zlib.gunzipSync(plain);
    }
    return JSON.parse(plain.toString("utf8"));
  } catch (err) {
    try {
      return JSON.parse(blob.toString("utf8"));
    } catch (_) {
      return {};
    }
  }
}

function requestHttp(url, headers, bodyBuffer) {
  return new Promise((resolve) => {
    const u = new URL(url);
    const req = https.request(
      {
        hostname: u.hostname,
        port: 443,
        path: u.pathname + u.search,
        method: "POST",
        headers,
        rejectUnauthorized: false,
        timeout: 20000,
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: Buffer.concat(chunks),
          });
        });
      }
    );
    req.on("error", (e) => {
      resolve({ statusCode: 500, headers: {}, body: Buffer.alloc(0), error: e.message });
    });
    if (bodyBuffer && bodyBuffer.length > 0) {
      req.write(bodyBuffer);
    }
    req.end();
  });
}

async function fetchApi(path, data = {}) {
  const p = "/" + path.replace(/^\/+/, "");
  const rid = crypto.randomUUID();
  const ts = Math.floor(Date.now() / 1000);
  const sign = crypto.createHash("sha256").update(`Dart|${SESSION_ID}|${rid}|${ts}|${p}`).digest("hex") + "-" + ts;
  const body = encryptBody(data, rid);

  const headers = {
    "User-Agent": USER_AGENT,
    Accept: "*/*",
    Origin: HOST,
    Referer: `${HOST}/home`,
    "Content-Type": "application/octet-stream",
    version: VERSION,
    deviceType: DEVICE_TYPE,
    time: String(ts),
    sign,
    requestId: rid,
    sessionId: SESSION_ID,
    deviceBrand: "",
    deviceModel: "",
    systemName: "",
    systemVersion: "",
    "Content-Length": String(body.length),
  };

  const url = `${API}${p}`;
  await OmniBox.log("info", `[黄豆短剧][request] ${url}`);

  // 优先使用原生 HTTPS 请求，避免 OmniBox.request 跨 IPC 传输二进制 Buffer 时被 UTF-8 字符串强制编码损坏
  let res = await requestHttp(url, headers, body);

  if (!res || !res.body || (Buffer.isBuffer(res.body) && res.body.length === 0)) {
    if (typeof OmniBox !== "undefined" && typeof OmniBox.request === "function") {
      try {
        res = await OmniBox.request(url, {
          method: "POST",
          headers,
          data: body,
          body,
          timeout: 20000,
        });
      } catch (e) {
        await OmniBox.log("warn", `[黄豆短剧][request] OmniBox.request error: ${e.message}`);
      }
    }
  }

  const rawBuf = getBodyBuffer(res);
  const json = decryptResponse(rawBuf, rid);
  await OmniBox.log(
    "info",
    `[黄豆短剧][response] ${p} status=${res?.statusCode || 0} bytes=${rawBuf.length} resStatus=${json?.status || "fail"}`
  );
  return json;
}

function extractList(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  if (Array.isArray(data.list)) return data.list;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.data)) return data.data;
  if (data.data && typeof data.data === "object") return extractList(data.data);
  return [];
}

function getPic(item = {}) {
  return item.img_y || item.img_x || item.img || item.cover || item.pic || "";
}

function mapVod(item = {}) {
  const vid = cleanSid(item.id || item.drama_id || "");
  const remarks = item.update_label || item.corner || (item.episode_count ? `全${item.episode_count}集` : "");
  return {
    vod_id: vid,
    vod_name: text(item.name || item.title || item.t || vid),
    vod_pic: text(getPic(item)),
    vod_remarks: text(remarks),
    vod_year: "",
    type_id: text(item.cat_id || item.category || ""),
    type_name: text(item.category || item.type || "短剧"),
  };
}

async function getClasses() {
  if (classCache) return classCache;
  const arr = [{ type_id: "all", type_name: "全部短剧" }];
  const data = await fetchApi("/drama/navList", {});
  const list = extractList(data?.data || data);
  for (const item of list) {
    const tid = text(item.code || item.id || item.cat_id || "");
    const name = text(item.name || item.title || tid);
    if (tid && name) {
      arr.push({ type_id: tid, type_name: name });
    }
  }
  classCache = arr;
  return arr;
}

async function getNavFilter(code) {
  if (!filterCache[code]) {
    const data = await fetchApi("/drama/navFilter", { code: String(code) });
    filterCache[code] = extractList(data?.data || data);
  }
  return filterCache[code] || [];
}

async function getFilters(classes) {
  const common = [
    {
      key: "order",
      name: "排序",
      value: [
        { name: "默认", value: "" },
        { name: "最新", value: "new" },
        { name: "最热", value: "hot" },
      ],
    },
    {
      key: "update_status",
      name: "状态",
      value: [
        { name: "全部", value: "" },
        { name: "连载", value: "0" },
        { name: "完结", value: "1" },
      ],
    },
  ];

  const fs = {};
  for (const c of classes) {
    const tid = c.type_id;
    const tabs = tid !== "all" && tid !== "yuandou" ? await getNavFilter(tid) : [];
    const filterList = [];
    if (tabs.length > 0) {
      filterList.push({
        key: "sub",
        name: "子分类",
        value: tabs.map((t, idx) => ({ name: text(t.name || "默认"), value: String(idx) })),
      });
    }
    filterList.push(...common);
    fs[tid] = filterList;
  }
  return fs;
}

async function home(params, context) {
  try {
    const classes = await getClasses();
    const filters = await getFilters(classes);
    const res = await fetchApi("/drama/list", { page: "1", page_size: "18" });
    const list = extractList(res).map(mapVod);
    await OmniBox.log("info", `[黄豆短剧][home] class=${classes.length} list=${list.length}`);
    return { class: classes, filters, list };
  } catch (e) {
    await OmniBox.log("error", `[黄豆短剧][home] ${e.message}`);
    return { class: [], filters: {}, list: [] };
  }
}

async function category(params, context) {
  try {
    const tid = text(params.categoryId || params.type_id || "all");
    const page = Math.max(1, parseInt(params.page || 1, 10));
    const f = params.filters || {};

    let items = [];
    if (tid === "yuandou") {
      const data = await fetchApi("/drama/navBlock", { code: "yuandou", tab: "recommend", page: String(page) });
      const blocks = extractList(data?.data || data);
      for (const b of blocks) {
        if (b && Array.isArray(b.items)) items.push(...b.items);
        else if (b && (b.id || b.drama_id)) items.push(b);
      }
    } else {
      const req = { page: String(page), page_size: "18" };
      if (tid && tid !== "all" && tid !== "recommend") {
        const tabs = await getNavFilter(tid);
        const idx = parseInt(f.sub || 0, 10);
        const sub = tabs && idx >= 0 && idx < tabs.length ? tabs[idx] : {};
        const flt = sub.filter || {};
        req.cat_id = flt.cat_id || "";
        if (flt.tag_id) req.tag_id = flt.tag_id;
        req.order = flt.order || f.order || "";
      } else if (f.order) {
        req.order = f.order;
      }
      if (f.update_status) {
        req.update_status = f.update_status;
      }
      const data = await fetchApi("/drama/list", req);
      items = extractList(data);
    }

    const list = items.map(mapVod);
    await OmniBox.log("info", `[黄豆短剧][category] tid=${tid} page=${page} list=${list.length}`);
    return {
      page,
      pagecount: page + (list.length >= 18 ? 1 : 0),
      total: page * 18 + (list.length >= 18 ? 1 : 0),
      list,
    };
  } catch (e) {
    await OmniBox.log("error", `[黄豆短剧][category] ${e.message}`);
    return { page: 1, pagecount: 0, total: 0, list: [] };
  }
}

async function detail(params, context) {
  try {
    const vid = cleanSid(params.videoId || params.id || "");
    if (!vid) return { list: [] };

    const obj = await fetchApi("/drama/detail", { id: vid });
    const data = obj?.data || obj || {};
    if (!data || typeof data !== "object") return { list: [] };

    const vodId = cleanSid(data.id || data.drama_id || vid);
    const name = text(data.name || data.title || data.t || vodId);
    const eps = Array.isArray(data.episodes) ? data.episodes : [];
    const count = parseInt(data.episode_count || data.free_episodes || eps.length || 1, 10);

    const episodes = [];
    if (eps.length > 0) {
      for (let i = 0; i < eps.length; i++) {
        const ep = eps[i];
        const seq = String(ep.seq || ep.episode || ep.ep || i + 1);
        const epName = text(ep.name || ep.title || `第${seq}集`);
        episodes.push({
          name: epName,
          playId: JSON.stringify({ vodId, seq, episodeName: epName, title: name }),
        });
      }
    } else {
      for (let i = 1; i <= count; i++) {
        episodes.push({
          name: `第${i}集`,
          playId: JSON.stringify({ vodId, seq: String(i), episodeName: `第${i}集`, title: name }),
        });
      }
    }

    await OmniBox.log("info", `[黄豆短剧][detail] vid=${vodId} name=${name} episodes=${episodes.length}`);

    return {
      list: [
        {
          vod_id: vodId,
          vod_name: name,
          vod_pic: text(getPic(data)),
          type_name: text(data.category || data.type || "短剧"),
          vod_remarks: text(data.update_label || `全${count}集`),
          vod_year: "",
          vod_area: "大陆",
          vod_lang: "国语",
          vod_director: "短剧",
          vod_actor: "短剧",
          vod_content: text(data.description || data.summary || name),
          vod_play_sources: episodes.length ? [{ name: "黄豆线路", episodes }] : [],
        },
      ],
    };
  } catch (e) {
    await OmniBox.log("error", `[黄豆短剧][detail] ${e.message}`);
    return { list: [] };
  }
}

async function search(params, context) {
  try {
    const keyword = text(params.keyword || params.wd || params.key || "");
    const page = Math.max(1, parseInt(params.page || 1, 10));
    if (!keyword) return { page, pagecount: 0, total: 0, list: [] };

    const data = await fetchApi("/drama/list", { page: String(page), page_size: "18", keywords: keyword });
    const items = extractList(data);
    const list = items.map(mapVod);

    await OmniBox.log("info", `[黄豆短剧][search] keyword=${keyword} page=${page} list=${list.length}`);
    return {
      page,
      pagecount: page + (list.length >= 18 ? 1 : 0),
      total: page * 18 + (list.length >= 18 ? 1 : 0),
      list,
    };
  } catch (e) {
    await OmniBox.log("error", `[黄豆短剧][search] ${e.message}`);
    return { page: 1, pagecount: 0, total: 0, list: [] };
  }
}

async function play(params, context) {
  try {
    const raw = text(params.playId || params.id || "");
    let vodId = "";
    let seq = "1";
    let episodeName = "";
    let title = "";

    try {
      const parsed = JSON.parse(raw);
      vodId = cleanSid(parsed.vodId || parsed.id);
      seq = String(parsed.seq || "1");
      episodeName = text(parsed.episodeName || params.episodeName || "");
      title = text(parsed.title || params.title || "");
    } catch (_) {
      if (raw.includes("|")) {
        const parts = raw.split("|");
        vodId = cleanSid(parts[0]);
        seq = parts[1] || "1";
      } else {
        vodId = cleanSid(raw);
      }
    }

    await OmniBox.log("info", `[黄豆短剧][play] vodId=${vodId} seq=${seq}`);

    const obj = await fetchApi("/drama/play", { id: vodId, seq });
    const data = obj?.data || {};
    let url = text(data.m3u8 || data.url || "");
    if (!url && Array.isArray(data.lines) && data.lines.length > 0) {
      url = text(data.lines[0].url || "");
    }
    if (!url) {
      url = `${HOST}/api/drama/hls/${vodId}/${seq}/play.m3u8?line=free`;
    }

    const header = {
      "User-Agent": USER_AGENT,
      Referer: `${HOST}/home`,
      Origin: HOST,
    };

    const historyPayload = {
      vodId,
      title: title || vodId,
      episode: raw,
      sourceId: context?.sourceId,
      episodeNumber: parseInt(seq, 10) || undefined,
      episodeName: episodeName || `第${seq}集`,
      playUrl: url,
      playHeader: header,
    };

    try {
      if (historyPayload.sourceId && typeof OmniBox.addPlayHistory === "function") {
        OmniBox.addPlayHistory(historyPayload).catch(() => {});
      }
    } catch (_) {}

    await OmniBox.log("info", `[黄豆短剧][play] success url=${url}`);

    return {
      parse: 0,
      urls: [{ name: "默认", url }],
      header,
      danmaku: [],
    };
  } catch (e) {
    await OmniBox.log("error", `[黄豆短剧][play] ${e.message}`);
    return { parse: 0, urls: [], header: {}, danmaku: [] };
  }
}
