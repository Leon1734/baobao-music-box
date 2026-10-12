/**
 * lx-loader.js — 在 Node 里执行洛雪音源 JS（宝宝音乐盒 · 2026-10 v2）
 *
 * 背景：HYW HTTP API（103.79.184.97）不稳定时，在线取链全军覆没；洛雪客户端能播
 * 是因为它本地执行这些 JS。本 loader 把「音源/」目录的 .js 真正跑起来。
 *
 * ⚠ 关键认知（v1 失败根因）：这些源注册用的是**顶层裸函数** `on(EVENT_NAMES.request, ...)`
 *   和 `send(...)` —— 是洛雪注入的**全局**，不是 `lx.on`。v1 只设了 globalThis.lx，
 *   裸 on 未定义 → eval 直接抛 ReferenceError → 所有源加载失败。
 *
 * CLI 用法:
 *   node tools/lx-loader.js <source> <songId> <quality> [name] [artist]
 * 输出: stdout 单行 JSON {url, via, ms} 或 {error}
 *       stderr 诊断日志
 */
'use strict';
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const vm = require('vm');

// 音源目录：优先用宿主指定的（server.py 传 MB_SOURCES —— exe 场景下指向 exe 同级「音源/」，
// 用户放了自己的音源能覆盖内置的）；没指定就用包内/项目内的「音源/」
const SOURCE_DIR = process.env.MB_SOURCES || path.resolve(__dirname, '..', '音源');

// ---------- 洛雪全局环境（裸 on/send + EVENT_NAMES） ----------
const EVENT_NAMES = {
  request: 'request',
  response: 'response',
  inited: 'inited',
  updateAlert: 'updateAlert',
  toggleSource: 'toggleSource',
};

// ---------- HTTP 基础（返回带 body/text/json 的结果对象） ----------
function httpToResult(url, opts, timeoutMs) {
  return new Promise((resolve, reject) => {
    let u;
    try { u = new URL(url); } catch (e) { return reject(new Error('bad url: ' + url.slice(0, 80))); }
    const mod = u.protocol === 'https:' ? https : http;
    const req = mod.request(u, opts, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const body = Buffer.concat(chunks);
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body,
          text: () => body.toString('utf8'),
          json: () => JSON.parse(body.toString('utf8')),
        });
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs || 15000, () => req.destroy(new Error('timeout')));
    if (opts.body) req.write(opts.body);
    req.end();
  });
}
// 源在 init 时可能发异步请求，失败会变成 unhandledRejection 把进程干掉 —— 全局兜住
if (typeof process !== 'undefined') {
  process.on('uncaughtException', () => {});
  process.on('unhandledRejection', () => {});
}

function normalizeHeaders(h) {
  const out = {};
  for (const [k, v] of Object.entries(h || {})) {
    if (v !== undefined && v !== null) out[k] = Array.isArray(v) ? v.join(', ') : String(v);
  }
  return out;
}

// ⚠ 洛雪 lx.request 有两种调用形态，必须都支持（只支持一种 = 源无限挂起）：
//   A) Promise 风格:  const res = await lx.request({url, method, headers, body, form})
//   B) callback 风格: lx.request(url, options, (err, resp, body) => {...})   ← needle 式，多数源用这个
function lxRequest(arg1, arg2, arg3) {
  let url, opts = {}, cb = null;
  if (typeof arg1 === 'string') {
    url = arg1;
    if (typeof arg2 === 'function') cb = arg2;
    else { opts = arg2 || {}; if (typeof arg3 === 'function') cb = arg3; }
  } else if (arg1 && typeof arg1 === 'object') {
    opts = arg1; url = opts.url || opts.uri;
    if (typeof arg2 === 'function') cb = arg2;
    if (typeof arg3 === 'function') cb = arg3;
  }
  if (!url) return cb ? cb(new Error('lx.request: no url')) : Promise.reject(new Error('lx.request: no url'));
  const p = doRequest(String(url), opts);
  if (cb) {
    p.then(res => {
      try {
        const text = res.body.toString('utf8');
        let parsed = text;
        try { parsed = JSON.parse(text); } catch (_) {}
        cb(null, { statusCode: res.statusCode, statusMessage: '', headers: res.headers, body: parsed }, parsed);
      } catch (e) { cb(e); }
    }).catch(e => cb(e));
    return;
  }
  return p;
}

async function doRequest(url, options = {}) {
  const method = ((typeof options === 'object' && options.method) || 'GET').toUpperCase();
  const headers = normalizeHeaders(typeof options === 'object' ? options.headers : null);
  let body = typeof options === 'object' ? options.body : null;
  if (typeof options === 'object' && options.form) {
    body = typeof options.form === 'string' ? options.form : new URLSearchParams(options.form).toString();
    if (!headers['Content-Type']) headers['Content-Type'] = 'application/x-www-form-urlencoded';
  }
  if (typeof options === 'object' && options.formData) {
    body = options.formData;   // 已是字符串的 multipart
    if (!headers['Content-Type']) headers['Content-Type'] = 'application/x-www-form-urlencoded';
  }
  if (body && typeof body !== 'string') { try { body = JSON.stringify(body); } catch (_) { body = String(body); } }
  const res = await httpToResult(url, { method, headers, body },
    (typeof options === 'object' && options.timeout) || 15000);
  return {
    statusCode: res.statusCode,
    headers: res.headers,
    body: res.text(),               // callback 风格里 body 是已解析值；Promise 风格里当字符串用
    raw: res.body,
    text: res.text,
    json: res.json,
  };
}

// fetch 风格（星海等新源直接用全局 fetch）
async function fetchImpl(input, init = {}) {
  const url = typeof input === 'string' ? input : (input && input.url) || String(input);
  const headers = normalizeHeaders(init.headers);
  let body = init.body;
  if (body && typeof body !== 'string') { try { body = JSON.stringify(body); } catch (_) { body = String(body); } }
  const res = await httpToResult(url, { method: ((init.method) || 'GET').toUpperCase(), headers, body }, init.timeout || 15000);
  return {
    ok: res.statusCode >= 200 && res.statusCode < 300,
    status: res.statusCode,
    headers: res.headers,
    text: res.text,
    json: res.json,
    arrayBuffer: async () => res.body,
  };
}

// 构建一个源专用的沙箱（共享全局工具，但 on/send 捕捉到该源自己的 handler）
function makeSandbox(capture) {
  const sandboxGlobal = {
    console, setTimeout, setInterval, clearTimeout, clearInterval, setImmediate,
    URL, URLSearchParams, Buffer, Promise, Symbol, Proxy, Reflect,
    String, Number, Boolean, Array, Object, JSON, Math, Date, RegExp, Error, TypeError,
    parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent,
    TextEncoder: require('util').TextEncoder,
    TextDecoder: require('util').TextDecoder,
    require: undefined, module: undefined, exports: undefined,     // 防源里 require
  };
  sandboxGlobal.globalThis = sandboxGlobal;
  sandboxGlobal.window = sandboxGlobal;
  sandboxGlobal.self = sandboxGlobal;
  sandboxGlobal.global = sandboxGlobal;
  sandboxGlobal.navigator = { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36', platform: 'win32' };
  sandboxGlobal.location = { href: 'https://ts.tempdomain.lx/', protocol: 'https:', origin: 'https://ts.tempdomain.lx', host: 'ts.tempdomain.lx' };
  sandboxGlobal.document = {
    addEventListener: () => {}, removeEventListener: () => {},
    createElement: () => ({ style: {}, setAttribute: () => {}, appendChild: () => {} }),
    head: { appendChild: () => {} }, body: { appendChild: () => {} },
    cookie: '',
  };
  sandboxGlobal.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  sandboxGlobal.fetch = fetchImpl;
  // ⚠ 洛雪源常用而我最初漏掉的全局（漏了会导致源的加密/解密静默失败 → 请求发到垃圾 URL → 超时）
  sandboxGlobal.atob = s => Buffer.from(String(s), 'base64').toString('binary');
  sandboxGlobal.btoa = s => Buffer.from(String(s), 'binary').toString('base64');
  sandboxGlobal.performance = { now: () => Date.now(), timeOrigin: Date.now() };
  const nodeCrypto = require('crypto');
  const webcrypto = nodeCrypto.webcrypto || nodeCrypto;
  sandboxGlobal.crypto = {
    getRandomValues: arr => { nodeCrypto.randomFillSync(arr); return arr; },
    randomUUID: () => nodeCrypto.randomUUID(),
    subtle: webcrypto.subtle,
  };
  sandboxGlobal.XMLHttpRequest = class {
    open() {} setRequestHeader() {} send() { if (this.onload) try { this.onload(); } catch (_) {} }
    abort() {} addEventListener(ev, fn) { if (ev === 'load' && fn) { this.onload = fn; } }
  };
  sandboxGlobal.WebSocket = class { constructor(){ } close(){} send(){} };
  sandboxGlobal.alert = () => {}; sandboxGlobal.confirm = () => true; sandboxGlobal.prompt = () => '';
  sandboxGlobal.EVENT_NAMES = EVENT_NAMES;
  sandboxGlobal.on = (event, fn) => {
    if (event === EVENT_NAMES.request && typeof fn === 'function') capture.handler = fn;
  };
  sandboxGlobal.send = (event, data) => {
    if (event === EVENT_NAMES.inited) capture.inited = data;
  };
  sandboxGlobal.lx = {
    version: '2.7.0', env: 'desktop', isDev: false,
    EVENT_NAMES,
    on: sandboxGlobal.on, send: sandboxGlobal.send,
    request: lxRequest,
    utils: {
      buffer: {
        from: (a, b) => Buffer.from(a, b),
        bufToString: (buf, enc) => Buffer.from(buf).toString(enc || 'utf8'),
      },
      crypto: {
        md5: s => require('crypto').createHash('md5').update(s).digest('hex'),
        randomBytes: n => require('crypto').randomBytes(n),
        aesEncrypt: (data, mode, key, iv) => {
          const c = require('crypto').createCipheriv(mode, key, iv);
          return Buffer.concat([c.update(data), c.final()]);
        },
      },
    },
  };
  return sandboxGlobal;
}

// ---------- 源清单（优先级序） ----------
const PREFERRED = [
  'xinghai-music-sourcev2.3.13.js',          // 星海：全平台+FLAC，独立 API
  'lx-music-source-v6 (修复).js',            // 独家 v6
  '长青SVIP音源(二改修复版) v1.2.0.js',
  'K×H测试 v1.7.17.js',                      // 多源聚合回退
  '独家音源-v5.js',
];

function loadSources(verbose) {
  const loaded = [];
  const names = PREFERRED.filter(n => fs.existsSync(path.join(SOURCE_DIR, n)));
  for (const f of fs.readdirSync(SOURCE_DIR).filter(x => x.endsWith('.js'))) {
    if (!names.includes(f)) names.push(f);
  }
  for (const name of names) {
    const capture = { handler: null, inited: null };
    try {
      const code = fs.readFileSync(path.join(SOURCE_DIR, name), 'utf8');
      const sandbox = makeSandbox(capture);
      vm.runInNewContext(code, sandbox, { filename: name, timeout: 20000 });
      if (typeof capture.handler === 'function') {
        loaded.push({ name, handler: capture.handler, inited: capture.inited });
        if (verbose !== false) console.error(`[loader] ✅ ${name}`);
      } else {
        if (verbose !== false) console.error(`[loader] ⚠️ ${name} 未注册 request handler`);
      }
    } catch (e) {
      if (verbose !== false) console.error(`[loader] ❌ ${name}: ${String(e && e.message || e).slice(0, 120)}`);
    }
  }
  return loaded;
}

// ---------- 取链 ----------
const QUALITY_MAP = { '128k': '128k', '320k': '320k', 'flac': 'flac', 'flac24bit': '24bitHires', 'hires': '24bitHires', 'master': 'master' };

async function trySource(entry, source, songId, quality, name, artist) {
  const info = {
    musicInfo: {
      songmid: songId, hash: songId, songId, rid: songId, mid: songId, musicId: songId,
      copyrightId: songId,
      name: name || '', songName: name || '',
      singer: artist || '', artist: artist || '', albumName: '',
    },
    type: QUALITY_MAP[quality] || '320k',
  };
  return entry.handler({ source, action: 'musicUrl', info });
}

function extractUrl(r) {
  if (!r) return '';
  if (typeof r === 'string') return /^https?:\/\//.test(r) ? r : '';
  if (typeof r === 'object') {
    for (const k of ['url', 'code', 'data']) {
      const v = r[k];
      if (typeof v === 'string' && /^https?:\/\//.test(v)) return v;
      if (v && typeof v === 'object' && typeof v.url === 'string' && /^https?:\/\//.test(v.url)) return v.url;
    }
  }
  return '';
}

async function getMusicUrl(source, songId, quality, name, artist) {
  const loaded = loadSources(true);
  if (!loaded.length) return { error: 'no source loaded' };
  const errors = [];
  for (const entry of loaded) {
    try {
      const r = await Promise.race([
        trySource(entry, source, songId, quality, name, artist),
        new Promise((_, rej) => setTimeout(() => rej(new Error('source timeout 12s')), 12000)),
      ]);
      const url = extractUrl(r);
      if (url) return { url, via: entry.name };
      errors.push(`${entry.name}: 空结果`);
    } catch (e) {
      errors.push(`${entry.name}: ${String(e && e.message || e).slice(0, 60)}`);
    }
  }
  return { error: errors.join(' | ') };
}

// ---------- CLI ----------
if (require.main === module) {
  const [,, source, songId, quality, ...rest] = process.argv;
  const name = rest[0] || '', artist = rest.slice(1).join(' ') || '';
  if (!source || !songId) {
    console.log(JSON.stringify({ error: 'usage: node lx-loader.js <source> <songId> <quality> [name] [artist]' }));
    process.exit(1);
  }
  const t0 = Date.now();
  getMusicUrl(source, songId, quality || '320k', name, artist)
    .then(r => { console.log(JSON.stringify(Object.assign({ ms: Date.now() - t0 }, r))); process.exit(0); })
    .catch(e => { console.log(JSON.stringify({ error: String(e && e.message || e) })); process.exit(0); });
  setTimeout(() => { console.log(JSON.stringify({ error: 'global timeout' })); process.exit(0); }, 40000).unref();
}

module.exports = { loadSources, getMusicUrl, extractUrl, httpToResult, fetchImpl };
