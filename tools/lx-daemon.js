/**
 * lx-daemon.js — 常驻洛雪音源服务（宝宝音乐盒 · 2026-10）
 *
 * 为什么：每次 CLI 冷启动要加载 5 个源（vm.runInNewContext × 5，约 1~2s），
 * 加上取链竞速，单次 9~15s。常驻后源只加载一次，请求走内存 → 毫秒级分发。
 *
 * 协议（本地 HTTP，127.0.0.1:7373）:
 *   GET /geturl?source=kw&id=228908&quality=320k&name=晴天&artist=周杰伦
 *       → {"url": "...", "via": "源名", "ms": 1234}  或 {"error": "..."}
 *   GET /health → {"ok": true, "sources": [...]}
 *   GET /reload → 重新加载源
 *
 * server.py 的 _get_url 链路：HYW(8s) → lx-daemon → 跨源 → 直链。
 */
'use strict';
const http = require('http');
const { URL, URLSearchParams } = require('url');
const loader = require('./lx-loader.js');
const fetchImpl = loader.fetchImpl;     // ⚠ 必须：daemon 本文件没有定义 fetchImpl，
                                        //   之前 verifyUrl 一调用就 ReferenceError → 所有 URL 判"不可播" → 全部无歌可放

const PORT = parseInt(process.env.LX_PORT || '7373', 10);

// 启动即加载源（一次）
let sources = [];
let loadedAt = Date.now();
function reload() {
  const t0 = Date.now();
  sources = loader.loadSources(false);     // 静默加载
  loadedAt = Date.now();
  console.log(`[lx-daemon] 源加载完成: ${sources.length} 个 (${Date.now() - t0}ms)`);
}
reload();

// 简单请求缓存（URL 结果 TTL 10 分钟 —— 直链一般 30 分钟有效，留足余量）
const cache = new Map();
const CACHE_TTL = 10 * 60 * 1000;
function cacheGet(k) {
  const v = cache.get(k);
  if (!v) return null;
  if (Date.now() - v.ts > CACHE_TTL) { cache.delete(k); return null; }
  return v.val;
}
function cachePut(k, val) {
  if (cache.size > 300) {   // 简单容量控制
    for (const key of cache.keys()) { cache.delete(key); break; }   // 删最旧（Map 保序）
  }
  cache.set(k, { ts: Date.now(), val });
}

const QUALITY_MAP = { '128k': '128k', '320k': '320k', 'flac': 'flac', 'flac24bit': '24bitHires', 'hires': '24bitHires', 'master': 'master' };

// URL 可播性验证：Range 拉 2KB 查音频魔数 + Content-Range 总长
// ⚠ 两层都要验：
//   1) 魔数 —— 网易 outer/url 对 VIP 歌返回 HTTP 200 的 404 HTML（假链）
//   2) 总长 ≥ 1MB —— 酷我占位音频（「此歌曲无法播放」提示音）是合法 MP3，
//      ID3 魔数全对，只有 ~180KB/11 秒。真歌（128k 也好）至少 1MB+。
async function verifyUrl(url) {
  // ⚠ 竞速时 5 个源同时开跑，验证请求也会并发；kuwo CDN 偶发把并发 Range 请求挂起
  //   （单发 1s 内 206，并发下 15s 超时）。所以验证要 2 次机会。
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await Promise.race([
        fetchImpl(url, { method: 'GET', headers: { 'Range': 'bytes=0-2047', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' } }),
        new Promise(res => setTimeout(() => res(null), 6000)),
      ]);
      if (!res) { console.error(`[verify] ${url.slice(0, 70)} → 6s 无响应 (第${attempt}次)`); continue; }
      if (!res.ok && res.status !== 206) { console.error(`[verify] ${url.slice(0, 70)} → HTTP ${res.status}`); return false; }
      const cr = String((res.headers && res.headers['content-range']) || '');
      const total = parseInt((cr.split('/')[1] || '').trim(), 10) || 0;
      if (total > 0 && total < 1024 * 1024) { console.error(`[verify] ${url.slice(0, 70)} → 总长 ${(total / 1024).toFixed(0)}KB <1MB（占位音）`); return false; }
      const buf = await res.arrayBuffer();
      const b = Buffer.from(buf.slice(0, 16));
      if (b.length < 4) { console.error(`[verify] ${url.slice(0, 70)} → 响应过短 ${b.length}B`); return false; }
      if (b.slice(0, 3).toString() === 'ID3') return true;
      if (b[0] === 0xff && (b[1] & 0xe0) === 0xe0) return true;
      if (b.slice(4, 8).toString() === 'ftyp') return true;
      if (b.slice(0, 4).toString() === 'fLaC') return true;
      if (b.slice(0, 4).toString() === 'RIFF') return true;
      if (b.slice(0, 4).toString() === 'OggS') return true;
      console.error(`[verify] ${url.slice(0, 70)} → 非音频 魔数=${b.slice(0, 8).toString('hex')} 总长=${total}`);
      return false;
    } catch (e) { console.error(`[verify] ${url.slice(0, 70)} → ${e.message} (第${attempt}次)`); }
  }
  return false;
}

async function getUrl(source, id, quality, name, artist, hash) {
  const ck = `${source}|${id}|${quality}`;
  const hit = cacheGet(ck);
  if (hit) return Object.assign({ cached: true }, hit);

  // 并行竞速：所有源同时开跑，每个源「取链 + 验证可播」作为一个整体单元，
  // 谁先出「验证过的 URL」谁赢。串行逐源最坏 5×(12+8)s = 100s，并行后 ≈ 最慢单源的时间。
  const attempts = sources.map(entry => (async () => {
    const r = await Promise.race([
      (async () => {
        const info = {
          musicInfo: {
            songmid: id, hash: hash || id, songId: id, rid: id, mid: id, musicId: id, copyrightId: id,
            name: name || '', songName: name || '', singer: artist || '', artist: artist || '', albumName: '',
          },
          type: QUALITY_MAP[quality] || '320k',
        };
        return entry.handler({ source, action: 'musicUrl', info });
      })(),
      new Promise((_, rej) => setTimeout(() => rej(new Error('src-timeout-12s')), 12000)),
    ]);
    const url = loader.extractUrl(r);
    if (!url) throw new Error('空结果');
    const ok = await Promise.race([
      verifyUrl(url),
      new Promise(res => setTimeout(() => res(false), 8000)),
    ]);
    if (!ok) throw new Error('URL不可播');
    return { url, via: entry.name };
  })());

  // ⚠ 失败的 attempt 必须被吞成「永远 pending」—— 否则 Promise.race 会被最快的
  //   reject（如 HYW 200ms 报卡密过期）直接打成失败，其它还在跑的源被白白抛弃。
  const silent = attempts.map(p => p.catch(() => new Promise(() => {})));   // 失败 → 永不 settle
  const result = await Promise.race([
    ...silent,
    // 全部 attempt 都 settle 后仍无成功 → 才判负（收集错误信息）
    Promise.allSettled(attempts).then(rs => {
      const errs = rs.filter(x => x.status === 'rejected').map(x => String(x.reason && x.reason.message || x.reason).slice(0, 50));
      throw new Error(errs.join('|').slice(0, 300) || 'no source');
    }),
  ]).catch(e => ({ __fail: String(e && e.message || e) }));
  if (result && result.__fail) return { error: result.__fail.slice(0, 300) };
  cachePut(ck, result);
  return result;
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  const send = (code, obj) => {
    const body = JSON.stringify(obj);
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
    res.end(body);
  };
  if (u.pathname === '/health') {
    return send(200, { ok: true, sources: sources.map(s => s.name), loadedAt, cache: cache.size });
  }
  if (u.pathname === '/reload') {
    reload();
    return send(200, { ok: true, count: sources.length });
  }
  if (u.pathname === '/debug_verify') {     // 临时诊断：验证 URL 可播性
    const q = u.searchParams;
    const url = q.get('url');
    verifyUrl(url).then(ok => send(200, { ok, url }));
    return;
  }
  if (u.pathname === '/geturl') {
    const q = u.searchParams;
    const source = q.get('source') || 'kw';
    const id = q.get('id') || '';
    const quality = q.get('quality') || '320k';
    const name = q.get('name') || '';
    const artist = q.get('artist') || '';
    const hash = q.get('hash') || '';
    if (!id) return send(400, { error: 'no id' });
    const t0 = Date.now();
    getUrl(source, id, quality, name, artist, hash)
      .then(r => send(200, Object.assign({ ms: Date.now() - t0 }, r)))
      .catch(e => send(500, { error: String(e && e.message || e) }));
    return;
  }
  send(404, { error: 'not found' });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[lx-daemon] listening on http://127.0.0.1:${PORT}`);
});

// 自愈：崩了自动重启由 server.py 负责；这里只做优雅退出
process.on('SIGTERM', () => { server.close(() => process.exit(0)); });
process.on('uncaughtException', (e) => { console.error('[lx-daemon] uncaught:', e && e.message); });
process.on('unhandledRejection', () => {});
