"""端到端播放验证：模拟用户点歌 → /api/url → 拉流验证（真实可播性）。
覆盖 kw/wy/tx/kg/mg 各一首。判定标准：URL 有效 + 拉流首段是音频 + 总长>=1MB。
"""
import urllib.request, urllib.parse, json, time, ssl

BASE = 'http://127.0.0.1:8082'
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

def api(path, timeout=90, **kw):
    q = urllib.parse.urlencode(kw)
    with urllib.request.urlopen(f'{BASE}{path}?{q}', timeout=timeout) as r:
        return json.loads(r.read())

def audio_head_ok(url):
    """Range 拉头 2KB，验音频魔数 + 总长"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Range':'bytes=0-2047'})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            head = r.read(2048)
            cr = r.headers.get('Content-Range') or ''
        total = int((cr.split('/')[-1] if '/' in cr else '0').strip() or 0)
        is_audio = (head[:3]==b'ID3' or (head and head[0]==0xff and (head[1]&0xe0)==0xe0)
                    or head[4:8]==b'ftyp' or head[:4]==b'fLaC' or head[:4]==b'RIFF' or head[:4]==b'OggS')
        return is_audio, total
    except Exception as e:
        return False, 0

CASES = [('kw','晴天 周杰伦'), ('wy','晴天 周杰伦'), ('tx','晴天 周杰伦'), ('kg','晴天 周杰伦'), ('mg','晴天 周杰伦')]
ok_count = 0
results = []
for src, kw in CASES:
    try:
        d = api('/api/search', keyword=kw, source=src, limit=1, timeout=25)
        s = (d.get('songs') or [{}])[0]
        if not s.get('id'):
            results.append((src, '搜索空', '', 0)); continue
        t0 = time.time()
        u = api('/api/url', id=s['id'], source=src, name=s.get('name',''), artist=s.get('artist',''), quality='320k')
        dt = time.time() - t0
        url = u.get('url') or ''
        via = u.get('via') or ('?' if url else 'FAIL')
        if not url:
            results.append((src, '取链失败: ' + (u.get('error') or '')[:50], '', 0)); continue
        # 拉流验证（via=direct 的 antiserver 就是占位音源自己，同样验）
        is_audio, total = audio_head_ok(url)
        ok = is_audio and total >= 1048576
        if ok: ok_count += 1
        results.append((src, ('✅可播' if ok else ('❌占位音' if is_audio else '❌非音频')) + f' via={via:20s}' if False else '✅' if ok else '❌', via[:24], total))
    except Exception as e:
        results.append((src, f'ERR {str(e)[:60]}', '', 0))

print("========== 端到端播放验证 ==========")
for src, status, via, total in results:
    size = f"{total/1048576:.1f}MB" if total else "-"
    print(f"  {src}: {status:60s} {size}")
print(f"\n成功 {ok_count}/{len(CASES)}")
