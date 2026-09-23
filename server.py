"""
宝宝音乐盒 v3 - 完整版
HYW音源API直接调用 + 酷我API + 本地文件
"""
import http.server, socketserver, os, json, sys, urllib.parse, urllib.request, ssl, threading, time, concurrent.futures
from pathlib import Path

PORT = int(os.environ.get('MB_PORT', 8082))   # 可用环境变量换端口，避免多实例端口冲突

def _resolve_dirs():
    """解析 资源目录(只读) 与 数据目录(可写)，兼容源码运行和 PyInstaller 打包：
      · 源码运行：两者都是脚本所在目录
      · exe 运行：资源在 PyInstaller 解包目录(_MEIPASS)，
                  数据(照片/音源/缓存)在 exe 同级目录，方便用户自己放文件
    """
    if getattr(sys, 'frozen', False):
        res = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        data = Path(sys.executable).parent
    else:
        res = data = Path(__file__).parent
    return res, data

RES_DIR, DATA_DIR = _resolve_dirs()
BASE = DATA_DIR          # 兼容旧代码：可写数据都放这里
PHOTOS = DATA_DIR / "photos"
SOURCES = DATA_DIR / "音源"
KIDS_CACHE_FILE = DATA_DIR / "kids_cache.json"

def _resource(*names):
    """找只读资源：优先数据目录（用户可覆盖/自定义），退回打包内资源"""
    for n in names:
        p = DATA_DIR / n
        if p.exists():
            return p
    for n in names:
        p = RES_DIR / n
        if p.exists():
            return p
    return RES_DIR / names[0]

# HYW 音源密钥：不写死在源码里（会随仓库公开）。
# 取值优先级：环境变量 > 同级 config.json > 内置默认值
HYW_API = "http://103.79.184.97"
_DEFAULT_HYW_KEY = ""    # 公开仓库里留空；私用可在 config.json 配置

def _load_hyw_key():
    """密钥取值优先级：环境变量 > exe 同级 config.json > 打包内置 config.json
    （内置的那份是为了「免安装包开箱即用」；公开仓库的源码里不含它）"""
    k = os.environ.get('MB_HYW_KEY', '').strip()
    if k:
        return k
    for cfg_path in (DATA_DIR / "config.json", RES_DIR / "config.json"):
        try:
            cfg = json.loads(cfg_path.read_text('utf-8'))
            k = str(cfg.get('hyw_key', '')).strip()
            if k:
                return k
        except Exception:
            pass
    return _DEFAULT_HYW_KEY

HYW_KEY = _load_hyw_key()


def _seed_kids_cache():
    """首次运行：把打包内预热的 kids_cache.json 播种到数据目录。
    exe 用户第一次打开「儿童乐园」本来要等十几秒去上游重建，播种后立即有内容。"""
    try:
        if KIDS_CACHE_FILE.exists():
            return
        src = RES_DIR / "kids_cache.json"
        if src.exists() and src.resolve() != KIDS_CACHE_FILE.resolve():
            KIDS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            KIDS_CACHE_FILE.write_bytes(src.read_bytes())
            print("[KIDS] 已用内置预热门类初始化缓存", flush=True)
    except Exception as e:
        print(f"[KIDS] 预热播种失败（不影响使用）: {e}", flush=True)

# ============ 错误日志（写文件，方便 exe 用户反馈问题） ============
ERROR_LOG = DATA_DIR / "error.log"
_log_lock = threading.Lock()

def _log_error(msg):
    """把异常写到 error.log（同时打屏）。exe 模式下用户看不到堆栈，落盘才查得到。"""
    line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n'
    try:
        with _log_lock:
            # 超过 1MB 就轮转一次，避免无限增长
            if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > 1048576:
                ERROR_LOG.replace(ERROR_LOG.with_suffix('.log.1'))
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(line)
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass

# ============ 儿童专区分区表（关键词已实测有结果，见 DEVELOPMENT_PLAN_v4.md） ============
# ⚠ 酷我搜索接口并发会被限流（并发=空结果），必须串行+间隔+缓存
KIDS_SECTIONS = [
    {'id': 'classic', 'name': '经典儿歌', 'icon': '🐤',
     'kws': ['两只老虎', '小兔子乖乖', '数鸭子', '小星星', '虫儿飞', '丢手绢', '拔萝卜', '小燕子']},
    {'id': 'sleep', 'name': '哄睡摇篮曲', 'icon': '🌙',
     'kws': ['摇篮曲', '舒伯特摇篮曲', '勃拉姆斯摇篮曲', '宝宝睡觉']},
    {'id': 'cartoon', 'name': '动画主题曲', 'icon': '🐷',
     'kws': ['小猪佩奇 儿歌', '汪汪队 儿歌', '超级飞侠 儿歌', '熊出没 儿歌', '奥特曼 儿歌']},
    {'id': 'english', 'name': '英文儿歌', 'icon': '🔤',
     'kws': ['Baby Shark', 'Finger Family', 'Twinkle Twinkle Little Star', 'ABC Song']},
    {'id': 'guoxue', 'name': '启蒙国学', 'icon': '📖',
     'kws': ['三字经 儿歌', '弟子规 儿歌', '唐诗 儿歌']},
    {'id': 'story', 'name': '睡前故事', 'icon': '📚',
     'kws': ['睡前故事 儿童', '绘本故事 儿童']},
    {'id': 'artist', 'name': '儿歌歌手', 'icon': '🎤',
     'kws': ['宝宝巴士', '贝乐虎儿歌', '儿歌多多', '环尼宝贝']},
]
KIDS_TTL = 6 * 3600          # 分区缓存有效期 6 小时
_kids_lock = threading.Lock()
_kids_state = {'data': None, 'ts': 0, 'refreshing': False}

# 歌词缓存（内存 + 磁盘）：歌词来源链最长要十几秒，缓存后二次播放瞬时返回
LYRIC_TTL = 7 * 24 * 3600
LYRIC_CACHE_FILE = BASE / "lyric_cache.json"
_lyric_lock = threading.Lock()
_lyric_cache = {}
_lyric_dirty = False

def _lyric_cache_load():
    global _lyric_cache
    try:
        if LYRIC_CACHE_FILE.exists():
            _lyric_cache = json.loads(LYRIC_CACHE_FILE.read_text('utf-8'))
            print(f'[LYRIC] 缓存载入 {len(_lyric_cache)} 条')
    except Exception as e:
        print(f'[LYRIC] 缓存载入失败 {e}')
        _lyric_cache = {}

def _lyric_cache_save():
    """惰性落盘：由后台线程定期调用，避免每个请求都写盘"""
    global _lyric_dirty
    with _lyric_lock:
        if not _lyric_dirty: return
        try:
            LYRIC_CACHE_FILE.write_text(json.dumps(_lyric_cache, ensure_ascii=False), 'utf-8')
            _lyric_dirty = False
        except Exception as e:
            print(f'[LYRIC] 缓存落盘失败 {e}')

def _lyric_cache_put(key, data):
    global _lyric_dirty
    with _lyric_lock:
        _lyric_cache[key] = {'ts': time.time(), 'data': data}
        # 简单容量控制：超过 2000 条清掉最旧的一半
        if len(_lyric_cache) > 2000:
            items = sorted(_lyric_cache.items(), key=lambda kv: kv[1].get('ts', 0))
            for k, _ in items[:1000]:
                _lyric_cache.pop(k, None)
        _lyric_dirty = True


# HYW 音源 API 地址与密钥定义在文件开头（见 _load_hyw_key）——
# 密钥不写死在源码里，避免随仓库公开。

socketserver.TCPServer.allow_reuse_address = True
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 连接类异常：客户端提前断开时 write/send 会抛这些，属正常现象
CONN_ERRORS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
               ConnectionRefusedError, TimeoutError)

class H(http.server.SimpleHTTPRequestHandler):
    # 请求超时：防止半开连接长期占住线程
    # 注意：保持默认 HTTP/1.0（不启用 keep-alive）——HTTP/1.1 要求每个响应
    # 都有准确的 Content-Length，代理/流式响应一旦缺失客户端会一直挂着
    timeout = 60

    def handle_one_request(self):
        """客户端断开导致的异常不应打断服务，也不该刷 traceback"""
        try:
            super().handle_one_request()
        except CONN_ERRORS:
            self.close_connection = True

    def handle_error(self, request, client_address):
        """默认实现会把整个 traceback 打到 stderr；连接类异常静默，其它写日志文件"""
        import sys, traceback as _tb
        et, ev, tb = sys.exc_info()
        if et and issubclass(et, CONN_ERRORS):
            return
        try:
            _log_error(''.join(_tb.format_exception(et, ev, tb)))
        except Exception:
            pass

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(RES_DIR), **kw)

    def translate_path(self, path):
        """静态文件解析：先找打包内资源（player.html 等），
        找不到再回退到 exe/脚本同级目录（用户自己放的 photos 等）"""
        p = super().translate_path(path)
        try:
            rel = os.path.relpath(p, str(RES_DIR))
            if not rel.startswith('..'):
                alt = DATA_DIR / rel
                if not os.path.exists(p) and alt.exists():
                    return str(alt)
        except Exception:
            pass
        return p

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(p.path)
        Q = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
        try:
            if path == '/api/photos': return self.j(self._photos())
            if path == '/api/music': return self.j(self._local_music())
            if path == '/api/sources': return self.j(self._sources())
            if path == '/api/search': return self.j(self._search(Q.get('keyword',''), Q.get('source','kw'), int(Q.get('limit','30')), int(Q.get('page','1'))))
            if path == '/api/url': return self.j(self._get_url(Q))
            if path == '/api/lyric': return self.j(self._get_lyric(Q))
            if path == '/api/pic': return self.j(self._get_pic(Q))
            if path == '/api/pics': return self.j(self._get_pics_batch(Q.get('ids','')))
            if path == '/api/boards': return self.j(self._boards())
            if path == '/api/board': return self.j(self._board(Q.get('id','93'), int(Q.get('page','1'))))
            if path == '/api/hot': return self.j(self._hot())
            if path == '/api/tj': return self.j(self._tj())
            if path == '/api/kids': return self.j(self._kids(Q.get('refresh') == '1'))
            if path == '/api/kids/catalog': return self.j(self._kids_catalog())
            if path == '/api/playlists': return self.j(self._playlists(Q.get('kw', '儿歌'), int(Q.get('limit', '20'))))
            if path == '/api/health': return self.j(self._health())
            if path == '/api/playlist': return self.j(self._playlist(Q.get('id',''), int(Q.get('page','1'))))
            if path == '/api/proxy': return self._proxy(Q.get('url',''))
        except Exception as e:
            import traceback as _tb
            _log_error(f'[api] {path} 失败: {type(e).__name__}: {e}\n{_tb.format_exc()}')
            return self.j({'error': str(e)})
        super().do_GET()

    def j(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        # 客户端提前断开（用户快速切歌/刷新/关页面）时 write 会抛连接类异常。
        # 这是完全正常的现象，必须吞掉——否则会在日志刷 traceback，
        # 且 except 里再调 self.j() 会二次抛错直接逃逸出 handler。
        try:
            self.send_response(200)
            self.send_header('Content-type','application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)
        except CONN_ERRORS:
            pass

    def _get(self, url, headers=None, timeout=15):
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        if headers:
            for k,v in headers.items(): req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            print(f"[HTTP] {url} -> {e}")
            return None

    def _text(self, url, headers=None):
        """取纯文本响应体（酷我封面接口把真实图片 URL 放在 body 里，content-type 是 text/html）"""
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        req.add_header('Referer', 'https://www.kuwo.cn/')
        if headers:
            for k,v in headers.items(): req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            print(f"[HTTP] {url} -> {e}")
            return None

    def end_headers(self):
        """HTML/JS/CSS 一律禁用缓存：否则浏览器拿旧版页面，用户看到的“功能没实现”其实是缓存"""
        p = urllib.parse.urlparse(self.path).path.lower()
        if p.endswith(('.html', '.htm', '.js', '.css')) or p in ('/', ''):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    # ====== 照片 ======
    # 来源优先级：exe/脚本同级的 photos、photos_web（用户自己放的）
    #             → 打包内置的 photos_web（随 exe 分发，开箱即有轮播）
    # 展示时优先用 photos_web/ 的压缩版（单张 ~200KB），没有才回退原图。
    def _photos(self):
        web_dirs = [BASE / 'photos_web', RES_DIR / 'photos_web']
        src_dirs = [PHOTOS, RES_DIR / 'photos']
        IMG = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        out, seen = [], set()
        # 1) 原图：有压缩版就用压缩版，否则用原图
        for d in src_dirs:
            if not d.exists(): continue
            for f in sorted(d.iterdir()):
                if f.suffix.lower() not in IMG or f.stem in seen: continue
                seen.add(f.stem)
                web = None
                for wd in web_dirs:
                    p = wd / (f.stem + '.jpg')
                    if p.exists(): web = p; break
                if web:
                    out.append({'name': f.stem, 'url': '/photos_web/' + urllib.parse.quote(web.name)})
                else:
                    out.append({'name': f.stem, 'url': '/photos/' + urllib.parse.quote(f.name)})
        # 2) 只有压缩版（打包内置、用户没放原图）也算一张
        for d in web_dirs:
            if not d.exists(): continue
            for f in sorted(d.iterdir()):
                if f.suffix.lower() not in IMG or f.stem in seen: continue
                seen.add(f.stem)
                out.append({'name': f.stem, 'url': '/photos_web/' + urllib.parse.quote(f.name)})
        return out

    # ====== 本地音乐 ======
    def _local_music(self):
        songs = []
        for d in [BASE/'music', BASE/'audio', BASE/'songs']:
            if d.exists():
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() in ('.mp3','.wav','.flac','.ogg','.m4a'):
                        songs.append({'name':f.stem,'url':f'/{d.name}/{urllib.parse.quote(f.name)}','size':f.stat().st_size,'source':'local'})
        for f in BASE.iterdir():
            if f.is_file() and f.suffix.lower() in ('.mp3','.wav','.flac','.ogg','.m4a'):
                songs.append({'name':f.stem,'url':f'/{urllib.parse.quote(f.name)}','size':f.stat().st_size,'source':'local'})
        return songs

    # ====== 音源文件列表 ======
    def _sources(self):
        """音源文件：exe 同级的 音源/ 优先，其次打包内置的 音源/"""
        out, seen = [], set()
        for d in [SOURCES, RES_DIR / '音源']:
            if not d.exists(): continue
            for f in sorted(d.iterdir()):
                try:
                    if not f.is_file() or f.suffix != '.js' or f.stat().st_size <= 1000: continue
                except OSError:
                    continue
                if f.stem in seen: continue
                seen.add(f.stem)
                out.append({'name': f.stem, 'size': f.stat().st_size})
        return out

    # ====== 在线搜索 (酷我) ======
    def _search(self, kw, src='kw', limit=30, page=1):
        if not kw: return {'songs':[],'total':0}
        page = max(1, int(page or 1))
        if src == 'kw':
            pn = page - 1   # 酷我 pn 从 0 开始
            url = f'http://search.kuwo.cn/r.s?client=kt&all={urllib.parse.quote(kw)}&pn={pn}&rn={limit}&uid=794762570&ver=kwplayer_ar_9.2.2.1&vipver=1&show_copyright_off=1&newver=1&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vermerge=1&mobi=1&issubtitle=1'
            d = self._get(url)
            if d and d.get('abslist'):
                songs = []
                for s in d['abslist']:
                    mid = s.get('MUSICRID','').replace('MUSIC_','')
                    if not mid: continue
                    songs.append({'id':mid,'songmid':mid,'name':s.get('SONGNAME',''),'artist':s.get('ARTIST',''),'album':s.get('ALBUM',''),'duration':int(s.get('DURATION',0)),'source':'kw'})
                return {'songs':songs,'total':int(d.get('TOTAL',0)),'source':'kw','page':page}
        elif src == 'wy':
            offset = (page - 1) * limit
            url = f'https://music.163.com/api/search/get/web?s={urllib.parse.quote(kw)}&type=1&offset={offset}&limit={limit}'
            d = self._get(url, {'Referer':'https://music.163.com/'})
            if d and d.get('result') and d['result'].get('songs'):
                songs = [{'id':str(s['id']),'songmid':str(s['id']),'name':s['name'],
                          'artist':'/'.join([a['name'] for a in s.get('artists',[])]),
                          'album':s.get('album',{}).get('name',''),'duration':s.get('duration',0)//1000,'source':'wy'}
                         for s in d['result']['songs']]
                return {'songs':songs,'total':d['result'].get('songCount',0),'source':'wy','page':page}
        return {'songs':[],'total':0,'source':src,'page':page}

    # ====== HYW音源获取播放URL ======
    def _get_url(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        name = Q.get('name','')
        artist = Q.get('artist','')
        quality = Q.get('quality','320k') or '320k'
        if quality not in ('128k','320k','flac','flac24bit','hires','master'):
            quality = '320k'

        # 方式1: 通过HYW音源API
        # HYW 服务器时快时慢（实测 0.3s ~ 12s），所以：
        #   短超时先试一次 → 慢/失败就立刻走下面的酷我直链兜底（通常 <1s）
        #   → 兜底也不行再回来用长超时重试一次 HYW
        params = {'songId': sid, 'source': src, 'key': HYW_KEY, 'quality': quality}
        if name: params['name'] = name
        if artist: params['artist'] = artist
        query = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k,v in params.items() if v)
        url = f'{HYW_API}/api/music/url?{query}'

        def _hyw(timeout):
            d = self._get(url, timeout=timeout)
            if d and d.get('code') == 200:
                result = d.get('url') or d.get('data') or ''
                if isinstance(result, str) and result.startswith('http'):
                    return {'url': result, 'source': 'hyw', 'quality': d.get('actualQuality', quality)}
                if isinstance(result, dict) and result.get('url'):
                    return {'url': result['url'], 'source': 'hyw', 'quality': d.get('actualQuality', quality)}
            return None

        fast = _hyw(8)
        if fast:
            return fast

        # 方式2: 网易云直链
        if src in ('wy', 'netease'):
            return {'url': f'https://music.163.com/song/media/outer/url?id={sid}.mp3', 'source': 'netease'}

        # 方式3: 酷我直链兜底
        # ⚠ convert_url3 返回的是 JSON 文本，直接塞给 audio.src 会播放失败；convert_url 返回纯 URL
        if src == 'kw':
            try:
                u = f'http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={sid}&format=mp3&response=url'
                req = urllib.request.Request(u)
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                    txt = r.read().decode('utf-8', 'replace').strip()
                if txt.startswith('http'):
                    return {'url': txt, 'source': 'kw-direct'}
            except Exception as e:
                print(f'[URL] 酷我直链兜底失败: {e}')

        # 方式4: HYW 长超时再试一次（上面只是短超时没等到，不代表它真挂了）
        slow = _hyw(20)
        if slow:
            return slow

        return {'error': '无法获取播放链接'}

    # ====== 歌词 ======
    # ====== 歌词（并行竞速 + 缓存）======
    def _lyric_kuwo(self, sid):
        d = self._get(f'http://m.kuwo.cn/newh5/singles/songinfoandlrc?musicId={sid}', timeout=10)
        if d and d.get('status')==200 and d.get('data') and d['data'].get('lrclist'):
            lines = []
            for l in d['data']['lrclist']:
                t = float(l.get('time',0))
                txt = l.get('lineLyric','')
                if txt: lines.append(f'[{int(t//60):02d}:{t%60:05.2f}]{txt}')
            if lines:
                return {'lyric':'\n'.join(lines), 'source':'kuwo'}
        return None

    def _lyric_netease_direct(self, sid):
        d = self._get(f'https://music.163.com/api/song/lyric?id={sid}&lv=1',
                      {'Referer':'https://music.163.com/'}, timeout=10)
        if d and d.get('lrc') and d['lrc'].get('lyric'):
            return {'lyric': d['lrc']['lyric'], 'source':'netease'}
        return None

    def _lyric_netease_search(self, name, artist):
        kw = f'{name} {artist}'.strip()
        url = f'https://music.163.com/api/search/get/web?s={urllib.parse.quote(kw)}&type=1&offset=0&limit=3'
        sd = self._get(url, {'Referer':'https://music.163.com/'}, timeout=10)
        if not (sd and sd.get('result') and sd['result'].get('songs')):
            return None
        ids = [s['id'] for s in sd['result']['songs'][:3]]
        # 3 个候选并行取词，谁先命中用谁的（原来串行最多等 3 次超时）
        def fetch(nid):
            ld = self._get(f'https://music.163.com/api/song/lyric?id={nid}&lv=1',
                           {'Referer':'https://music.163.com/'}, timeout=8)
            if ld and ld.get('lrc') and ld['lrc'].get('lyric'):
                return {'lyric': ld['lrc']['lyric'], 'source':'netease-fallback'}
            return None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(ids)) as ex:
                for r in ex.map(fetch, ids):
                    if r: return r
        except Exception:
            pass
        return None

    def _lyric_hyw(self, src, sid):
        try:
            params = {'action':'lyric','source':src,'songId':sid,'key':HYW_KEY}
            q = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k,v in params.items())
            d = self._get(f'{HYW_API}/api/music/info?{q}', timeout=10)
            if d and d.get('code')==200:
                data = d.get('data',{})
                if isinstance(data, dict) and data.get('lyric'):
                    return {'lyric': data['lyric'], 'source':'hyw'}
        except Exception as e:
            print(f'[LYRIC] HYW兜底失败 {e}')
        return None

    def _get_lyric(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        name = Q.get('name','')
        artist = Q.get('artist','')
        key = f'{src}_{sid}'

        # 0) 缓存命中（立即返回，不占网络）
        with _lyric_lock:
            c = _lyric_cache.get(key)
            if c and time.time()-c.get('ts',0) < LYRIC_TTL:
                d = dict(c['data']); d['cached'] = True
                return d

        # 候选源：(优先级, 名称, 取词函数)  —— 优先级 0 最高
        cands = []
        if src == 'kw':
            cands.append((0, 'kuwo', lambda: self._lyric_kuwo(sid)))
        elif src == 'wy':
            cands.append((0, 'netease', lambda: self._lyric_netease_direct(sid)))
        if name:
            cands.append((1, 'netease-fallback', lambda: self._lyric_netease_search(name, artist)))
        cands.append((2, 'hyw', lambda: self._lyric_hyw(src, sid)))

        result = None
        all_pris = [c[0] for c in cands]
        GRACE_HIGH_PRI = 3.0   # 秒：为高优先级源保留的首屏等待窗口，超时先用快源
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(cands))
        t_start = time.time()
        try:
            futs = {pool.submit(fn): (pri, nm) for pri, nm, fn in cands}
            found = {}       # pri -> data（已成功拿到词的源）
            done_pri = set() # 已结束（无论成功失败）的优先级
            deadline = t_start + 12
            pending = set(futs)
            # ⚠ 用 wait(短超时) 轮询而不是 as_completed：as_completed 会阻塞到"有结果为止"，
            #   导致宽限期检查点永远不执行（慢源一拖就是十几秒）
            while pending:
                done, pending = concurrent.futures.wait(
                    pending, timeout=0.3, return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    pri, nm = futs[fut]
                    done_pri.add(pri)
                    try:
                        r = fut.result()
                    except Exception as e:
                        print(f'[LYRIC] {nm} 异常 {e}')
                        r = None
                    if r and r.get('lyric'):
                        found[pri] = r
                if found:
                    best = min(found)
                    # 最优已确定（更优优先级都已结束且无词）→ 立即用
                    if all(p in done_pri for p in all_pris if p < best):
                        break
                    # 超过宽限期 → 先用快源出歌词，优质源继续跑完后台更新缓存
                    if time.time() - t_start > GRACE_HIGH_PRI:
                        print(f'[LYRIC] 宽限期到，先用 {found[best].get("source")}，等待优质源后台补')
                        break
                if time.time() > deadline:
                    break
            if found:
                result = found[min(found)]
                # 后台补优：若更优优先级仍在跑，完成后写进缓存供下次使用
                if result is not None:
                    rp = min(found)
                    for f, (p, nm) in futs.items():
                        if p < rp and not f.done():
                            def _upgrade(fut2, _p=p):
                                try:
                                    r2 = fut2.result()
                                    if r2 and r2.get('lyric'):
                                        _lyric_cache_put(key, r2)
                                        print(f'[LYRIC] 后台补到更优歌词 {key} → {r2.get("source")}')
                                except Exception:
                                    pass
                            f.add_done_callback(_upgrade)
        except concurrent.futures.TimeoutError:
            print('[LYRIC] 竞速超时，使用已返回的结果')
            if found: result = found[min(found)]
        except Exception as e:
            print(f'[LYRIC] 竞速失败 {e}')
            # 极端情况回退到串行
            for pri, nm, fn in cands:
                try:
                    r = fn()
                    if r and r.get('lyric'):
                        result = r; break
                except Exception:
                    pass
        finally:
            pool.shutdown(wait=False)

        if result:
            _lyric_cache_put(key, result)
        return result or {'lyric':''}

    # ====== 封面 ======
    def _get_pic(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        if src == 'kw':
            # ⚠ artistpicserver 响应是 text/html，body 里才是真正的图片 URL
            #   （如 http://img1.kwcdn.kuwo.cn/star/albumcover/500/xxx.jpg）
            #   旧代码把这个接口 URL 直接当 <img src> 返回 → 浏览器按文本解析 → 封面永远不显示
            u = f'http://artistpicserver.kuwo.cn/pic.web?type=rid_pic&pictype=500&size=500&rid={sid}'
            real = self._text(u)
            if real:
                real = real.strip()
                if real.startswith('http'):
                    return {'url': real}
            return {'url': ''}
        if src == 'wy':
            d = self._get(f'https://music.163.com/api/song/detail?id={sid}&ids=[{sid}]', {'Referer':'https://music.163.com/'})
            if d and d.get('songs') and d['songs'][0].get('album',{}).get('picUrl'):
                return {'url': d['songs'][0]['album']['picUrl']}
        return {'url': ''}

    # ====== 批量封面（减少请求数）======
    def _get_pics_batch(self, ids_str):
        """ids=kw_123,kw_456 → {kw_123: url, ...}  最多50个"""
        if not ids_str:
            return {'covers': {}}
        items = [x.strip() for x in ids_str.split(',') if x.strip()][:50]
        covers = {}
        import concurrent.futures

        def fetch_one(key):
            try:
                if '_' not in key:
                    return key, ''
                src, sid = key.split('_', 1)
                if src == 'kw':
                    u = f'http://artistpicserver.kuwo.cn/pic.web?type=rid_pic&pictype=500&size=500&rid={sid}'
                    real = self._text(u)
                    if real:
                        real = real.strip()
                        if real.startswith('http'):
                            return key, real
                elif src == 'wy':
                    d = self._get(f'https://music.163.com/api/song/detail?id={sid}&ids=[{sid}]', {'Referer':'https://music.163.com/'})
                    if d and d.get('songs') and d['songs'][0].get('album',{}).get('picUrl'):
                        return key, d['songs'][0]['album']['picUrl']
            except Exception:
                pass
            return key, ''

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                for k, v in ex.map(fetch_one, items):
                    covers[k] = v
        except Exception as e:
            print(f'[PICS] 批量失败 {e}')
        return {'covers': covers}

    # ====== 排行榜 ======
    def _boards(self):
        return {'boards':[
            {'id':'93','name':'飙升榜','icon':'🔥'},{'id':'17','name':'新歌榜','icon':'🆕'},
            {'id':'16','name':'热歌榜','icon':'🎵'},{'id':'158','name':'抖音热歌榜','icon':'📱'},
            {'id':'284','name':'热评榜','icon':'💬'},{'id':'290','name':'ACG新歌榜','icon':'🎌'},
            {'id':'278','name':'古风音乐榜','icon':'🏮'},{'id':'242','name':'电音榜','icon':'🎧'},
            {'id':'187','name':'流行趋势榜','icon':'📈'},{'id':'186','name':'ACG神曲榜','icon':'🎮'},
            {'id':'26','name':'经典怀旧榜','icon':'📻'},{'id':'104','name':'华语榜','icon':'🇨🇳'},
            {'id':'64','name':'影视金曲榜','icon':'🎬'},{'id':'176','name':'DJ嗨歌榜','icon':'💃'},
            {'id':'12','name':'Billboard榜','icon':'🇺🇸'},{'id':'49','name':'iTunes榜','icon':'🍎'},
            {'id':'246','name':'YouTube榜','icon':'▶️'},{'id':'15','name':'日本公信榜','icon':'🇯🇵'},
        ]}

    def _board(self, bid, page=1):
        url = f'http://kbangserver.kuwo.cn/ksong.s?from=pc&fmt=json&pn={page-1}&rn=30&type=bang&data=content&id={bid}&show_copyright_off=0&pcmp4=1&isbang=1'
        d = self._get(url)
        if d and d.get('musiclist'):
            songs = []
            for s in d['musiclist']:
                mid = str(s.get('id','') or s.get('musicrid','')).replace('MUSIC_','')
                if not mid: continue
                dur = int(s.get('song_duration',0) or s.get('duration',0))
                songs.append({'id':mid,'songmid':mid,'name':s.get('name',''),'artist':s.get('artist',''),'album':s.get('album',''),'duration':dur,'source':'kw'})
            return {'songs':songs,'total':len(songs)}
        return {'songs':[],'total':0}

    # ====== 热搜词 ======
    def _hot(self):
        # 酷我热搜返回TEXT格式: "TEXT=word1\r\nword2\r\n..."
        try:
            req = urllib.request.Request('http://hotword.kuwo.cn/hotword.s?prodid=2&type=11&encoding=utf8')
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                text = r.read().decode('utf-8', errors='ignore')
            if text.startswith('TEXT='):
                text = text[5:]
            words = [w.strip() for w in text.replace('\r','').split('\n') if w.strip()]
            return {'words': words[:20]}
        except Exception as e:
            print(f'[HOT] {e}')
        return {'words':[]}

    # ====== 推荐歌单 ======
    def _tj(self):
        # 酷我PC端推荐歌单API
        url = 'http://wapi.kuwo.cn/api/pc/classify/playlist/getRcmPlayList?pn=1&rn=30&order=hot&pay=0'
        d = self._get(url, {'Referer':'https://www.kuwo.cn/','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        if d and d.get('code')==200 and d.get('data') and d['data'].get('data'):
            playlists = []
            for p in d['data']['data']:
                playlists.append({
                    'name': p.get('name',''),
                    'id': str(p.get('id','')),
                    'img': p.get('img',''),
                    'count': p.get('listencnt',0),
                    'total': p.get('total',0),
                    'author': p.get('uname','')
                })
            return {'playlists': playlists, 'total': d['data'].get('total',0)}
        return {'playlists':[]}

    # ====== 歌单详情 ======
    def _playlist(self, pid, page=1):
        url = f'http://nplserver.kuwo.cn/pl.svc?op=getlistinfo&pid={pid}&pn={page-1}&rn=50&encode=utf8&keyset=pl2012&identity=kuwo&pcmp4=1&vipver=1&newver=1'
        d = self._get(url)
        if d and d.get('musiclist'):
            songs = []
            for s in d['musiclist']:
                mid = str(s.get('id','') or s.get('rid','')).replace('MUSIC_','')
                if not mid: continue
                songs.append({
                    'id': mid, 'songmid': mid,
                    'name': s.get('name',''),
                    'artist': s.get('artist',''),
                    'album': s.get('album',''),
                    'duration': int(s.get('duration',0)),
                    'source': 'kw'
                })
            return {'songs': songs, 'total': d.get('total',0), 'name': d.get('title',''), 'pic': d.get('pic','')}
        return {'songs':[], 'total':0}

    # ====== 儿童专区（v4 新增）=======
    # ⚠ 酷我搜索接口【并发会被限流】：并发请求返回空结果，必须串行 + 间隔 + 落盘缓存
    KIDS_BAD_WORDS = ('dj', '串烧', '伴奏', 'remix', '翻唱', '纯音乐', '伴奏版')
    KIDS_GOOD_ARTISTS = ('贝乐虎', '儿歌多多', '宝宝巴士', '环尼宝贝', '海豹kid', '快乐听儿歌',
                         '儿歌', '贝瓦', '蓝迪', '亲宝')

    def _kids_norm_name(self, nm):
        """歌名归一化（去平台后缀/括号备注），用于同名去重"""
        import re as _re
        n = _re.sub(r'[|｜].*$', '', nm or '')                 # 去掉 "|免费听" 之类的平台后缀
        n = _re.sub(r'[\(（\[].*?[\)）\]]', '', n)              # 去掉 "(DJ版儿歌)" 等备注
        n = _re.sub(r'(免费|试听|新编|哄睡版|dj版|儿歌舞曲|动感儿歌|日语儿歌)', '', n, flags=_re.I)
        return _re.sub(r'\s+', '', n).strip().lower()

    def _kids_score(self, s):
        """儿歌内容质量打分：剔DJ串烧/剧集，优先儿歌原版"""
        import re as _re
        nm = (s.get('name') or ''); ar = (s.get('artist') or ''); dur = int(s.get('duration') or 0)
        sc = 0
        if any(b in nm.lower() for b in self.KIDS_BAD_WORDS): sc -= 40
        if _re.search(r'第\s*\d+\s*集', nm): sc -= 25          # 有声剧集，不是儿歌
        if any(g in ar for g in self.KIDS_GOOD_ARTISTS): sc += 20
        if 60 <= dur <= 220: sc += 10                          # 儿歌常规时长
        if dur and dur < 30: sc -= 30                          # 十几秒的试听碎片，直接压到底
        if len(nm) <= 14: sc += 6                              # 名字短=单曲，不是串烧大杂烩
        return sc

    def _kids_catalog(self):
        return {'sections': [{'id': s['id'], 'name': s['name'], 'icon': s['icon'], 'kws': s['kws']}
                             for s in KIDS_SECTIONS]}

    def _kids_load_disk(self):
        try:
            if KIDS_CACHE_FILE.exists():
                d = json.loads(KIDS_CACHE_FILE.read_text(encoding='utf-8'))
                if d.get('sections'):
                    _kids_state['data'] = d['sections']
                    _kids_state['ts'] = int(d.get('ts', 0))
                    print(f"[KIDS] 载入缓存 {len(d['sections'])} 个分区")
        except Exception as e:
            print(f'[KIDS] 缓存读取失败: {e}')

    def _kids_rebuild(self, cap=16):
        sections = []
        try:
            for sec in KIDS_SECTIONS:
                buckets = []
                for kw in sec['kws']:
                    try:
                        r = self._search(kw, 'kw', 12)
                    except Exception as e:
                        print(f'[KIDS] 搜索失败 {kw}: {e}'); r = {}
                    buckets.append(sorted(r.get('songs') or [], key=self._kids_score, reverse=True))
                    time.sleep(0.35)                      # ★ 串行间隔，避免被限流
                # 各关键词轮询抽取 + 同名去重 → 保证专区多样性，不被单一歌手刷屏
                songs, ids, names, i = [], set(), set(), 0
                while len(songs) < cap and any(i < len(b) for b in buckets):
                    for b in buckets:
                        if i < len(b):
                            s = b[i]
                            key = self._kids_norm_name(s.get('name', ''))
                            if s['id'] in ids or key in names: continue
                            ids.add(s['id']); names.add(key); songs.append(s)
                            if len(songs) >= cap: break
                    i += 1
                sections.append({'id': sec['id'], 'name': sec['name'], 'icon': sec['icon'], 'songs': songs})
                print(f'[KIDS] {sec["name"]}: {len(songs)} 首（去重后）')
            payload = {'sections': sections, 'ts': int(time.time()), 'version': 4}
            KIDS_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
            _kids_state['data'] = sections
            _kids_state['ts'] = payload['ts']
            return sections
        except Exception as e:
            print(f'[KIDS] 构建失败: {e}')
            return _kids_state['data'] or []
        finally:
            _kids_state['refreshing'] = False

    def _kids(self, force=False):
        now = time.time()
        with _kids_lock:
            if _kids_state['data'] is None:
                self._kids_load_disk()
            have = bool(_kids_state['data'])
            age = int(now - _kids_state['ts']) if _kids_state['ts'] else 0
            if have and not force:
                if age < KIDS_TTL:
                    return {'sections': _kids_state['data'], 'cached': True, 'age': age}
                # 过期：先返回旧数据（秒开），后台静默刷新
                if not _kids_state['refreshing']:
                    _kids_state['refreshing'] = True
                    threading.Thread(target=self._kids_rebuild, daemon=True).start()
                return {'sections': _kids_state['data'], 'cached': True, 'stale': True, 'age': age, 'refreshing': True}
            if _kids_state['refreshing'] and not force:
                return {'sections': _kids_state['data'] or [], 'cached': True, 'building': True}
        sections = self._kids_rebuild()                   # 首次或强制：同步构建
        return {'sections': sections, 'cached': False, 'age': 0}

    # ====== 精选歌单（儿童专区图片入口）======
    def _playlists(self, kw='儿歌', limit=20):
        url = ('http://search.kuwo.cn/r.s?client=kt&all=' + urllib.parse.quote(kw) +
               f'&pn=0&rn={limit}&ft=playlist&encoding=utf8&rformat=json&show_copyright_off=1&vipver=1&newver=1&mobi=1')
        d = self._get(url)
        out = []
        for p in ((d or {}).get('abslist') or []):
            pid = str(p.get('playlistid') or p.get('DC_TARGETID') or '')
            if not pid or pid == 'None': continue
            out.append({'id': pid, 'name': p.get('name', ''), 'pic': p.get('pic') or p.get('hts_pic', ''),
                        'songnum': int(p.get('songnum') or 0), 'tags': p.get('tags', ''),
                        'playcnt': int(p.get('playcnt') or 0), 'author': p.get('nickname', ''),
                        'intro': p.get('intro', '')})
        return {'playlists': out, 'total': len(out), 'keyword': kw}

    def _health(self):
        return {'ok': True, 'app': 'baobao-music', 'port': PORT,
                'data_dir': str(DATA_DIR),
                'photos': len(self._photos()), 'local_songs': len(self._local_music()),
                'kids_sections': len(_kids_state['data'] or []),
                'kids_age_s': int(time.time() - _kids_state['ts']) if _kids_state['ts'] else None,
                'kids_cache_file': KIDS_CACHE_FILE.exists()}

    # ====== 音频代理 (解决CORS问题) ======
    def _proxy(self, url):
        """音频代理：支持 Range 请求（拖动进度条）+ CORS（均衡器用）"""
        if not url or not url.startswith('http'):
            return self.j({'error': 'invalid url'})
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            # 透传 Range（seek 必需）
            rng = self.headers.get('Range')
            if rng:
                req.add_header('Range', rng)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                content_type = r.headers.get('Content-Type', 'audio/mpeg')
                total = r.headers.get('Content-Length')
                content_range = r.headers.get('Content-Range')
                status = r.status
                # 先读第一块再发响应头：酷我 CDN 偶发返回 206 但 body 为空
                # （限流/失效链接）。若先把头发出去就只能给客户端一个 0 字节流，
                # 浏览器会永远停在 readyState=0 —— 必须在这里就判失败，让前端重试换链。
                first = r.read(65536)
                if not first:
                    raise IOError('上游返回空数据（链接失效或被限流）')
                self.send_response(status if status in (200, 206) else 200)
                self.send_header('Content-Type', content_type)
                if total:
                    self.send_header('Content-Length', total)
                if content_range:
                    self.send_header('Content-Range', content_range)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Expose-Headers', 'Content-Length,Content-Range,Accept-Ranges')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                # 流式传输（避免大文件占内存）
                self.wfile.write(first)
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except CONN_ERRORS:
            pass                       # 客户端断开，无需响应
        except Exception as e:
            try:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', '0')
                self.end_headers()
            except CONN_ERRORS:
                pass

    def do_HEAD(self):
        """音频代理的 HEAD 支持（浏览器预检）"""
        p = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(p.path)
        if path == '/api/proxy':
            Q = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
            url = Q.get('url','')
            if url and url.startswith('http'):
                try:
                    req = urllib.request.Request(url, method='HEAD')
                    req.add_header('User-Agent', 'Mozilla/5.0')
                    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                        self.send_response(200)
                        self.send_header('Content-Type', r.headers.get('Content-Type','audio/mpeg'))
                        if r.headers.get('Content-Length'):
                            self.send_header('Content-Length', r.headers.get('Content-Length'))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_header('Accept-Ranges', 'bytes')
                        self.end_headers()
                        return
                except Exception:
                    pass
        super().do_HEAD()

    def log_message(self, fmt, *args):
        msg = str(args[0]) if args else ''
        if not any(x in msg for x in ('.css','.woff','.ttf','.ico','.png','.jpg','.gif')):
            print(f"[MB] {msg}", flush=True)

    # 未实现的方法（外部扫描器/其它程序误连）直接 405，不要 501 + traceback
    def do_POST(self):     self._method_not_allowed()
    def do_PUT(self):      self._method_not_allowed()
    def do_DELETE(self):   self._method_not_allowed()
    def do_PATCH(self):    self._method_not_allowed()
    def do_OPTIONS(self):
        try:
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET,HEAD,OPTIONS')
            self.send_header('Access-Control-Allow-Headers', '*')
            self.end_headers()
        except CONN_ERRORS:
            pass

    def _method_not_allowed(self):
        try:
            self.send_response(405)
            self.send_header('Allow', 'GET, HEAD, OPTIONS')
            self.send_header('Content-Length', '0')
            self.end_headers()
        except CONN_ERRORS:
            pass

def _lyric_cache_flusher():
    """后台线程：每 30 秒把歌词缓存落盘一次（惰性写入，避免每个请求都写盘）"""
    while True:
        time.sleep(30)
        try:
            _lyric_cache_save()
        except Exception:
            pass

_srv = None          # 当前 Server 实例（None = 未启动/已关闭）
_fatal_stop = False  # True = 遇到不可恢复的错误（如端口被占），watchdog 不要再重启

class _Srv(socketserver.ThreadingTCPServer):
    """Windows 上 allow_reuse_address=True 会让第二个实例也绑上同一端口，
    结果两个进程互抢请求（用户看到的是「时而正常时而打不开」）。
    所以 Windows 下必须关掉它，让端口冲突直接报错、由上层给出明确提示。"""
    allow_reuse_address = (os.name != 'nt')
    daemon_threads = True


def _serve_worker():
    """实际服务循环：跑在独立线程里，任何异常都自愈重试，绝不静默退出"""
    global _srv
    while True:
        try:
            srv = _Srv(("", PORT), H)
            _srv = srv
            print(f"宝宝音乐盒 v3 启动! http://localhost:{PORT}/player.html", flush=True)
            srv.serve_forever(poll_interval=0.5)
            return                              # 正常返回 = 被 shutdown，交给主线程决定
        except OSError as e:
            # 端口已被占用（另一个实例还活着）：不要静默重试到天荒地老，
            # 也不要抢端口 —— 直接告诉用户去看那个实例，并让 watchdog 停止重启。
            global _fatal_stop
            _fatal_stop = True
            print(f"[提示] 端口 {PORT} 已被占用，无法启动：{e}", flush=True)
            print(f"       可能已有一个宝宝音乐盒在运行。先关掉它的窗口再试，", flush=True)
            print(f"       或者换个端口：宝宝音乐盒.exe --port 9000", flush=True)
            return
        except Exception as e:
            print(f'[FATAL] 服务异常: {type(e).__name__}: {e} —— 2 秒后重启', flush=True)
            if _srv is not None:
                try: _srv.server_close()
                except Exception: pass
                _srv = None
            time.sleep(2)

def _already_running():
    """检测是否已有实例在服务（Windows 上 SO_REUSEADDR 允许重复绑定同一端口，
    两个实例会互相抢请求，行为不可预测 —— 必须在绑定前拦掉）"""
    try:
        import urllib.request as _u
        with _u.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2) as r:
            d = json.loads(r.read().decode('utf-8'))
            return bool(d.get('ok')) and d.get('app') == 'baobao-music'
    except Exception:
        return False

def serve():
    """启动服务（阻塞）。源码运行和被 exe 调用都走这里。"""
    os.chdir(str(BASE))
    if _already_running():
        print(f"[提示] 已经有一个宝宝音乐盒在运行了（端口 {PORT}），本实例不重复启动。", flush=True)
        try:
            import urllib.request as _u
            with _u.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2) as r:
                _d = json.loads(r.read().decode('utf-8'))
            _other = _d.get('data_dir', '')
            if _other and os.path.normcase(_other) != os.path.normcase(str(DATA_DIR)):
                print(f"       注意：正在运行的那个用的是另一个目录：", flush=True)
                print(f"         {_other}", flush=True)
                print(f"       而当前目录是：{DATA_DIR}", flush=True)
                print(f"       它的照片/音源来自上面那个目录；想用当前目录，", flush=True)
                print(f"       请先关掉那个窗口再启动本程序。", flush=True)
        except Exception:
            pass
        print(f"       直接访问：http://localhost:{PORT}/player.html", flush=True)
        return False
    if not HYW_KEY:
        print("[提示] 未配置音源密钥（config.json 里的 hyw_key），在线取播放链接可能失败。", flush=True)
        print("       在线搜索/榜单仍可用，本地音乐播放不受影响。", flush=True)
    _lyric_cache_load()
    _seed_kids_cache()
    threading.Thread(target=_lyric_cache_flusher, daemon=True).start()
    # 服务线程 + 主线程守护：子线程无论因何退出（异常/端口被占/未知错误），
    # 主线程都能把它重新拉起，进程永不静默死掉
    while True:
        _t = threading.Thread(target=_serve_worker, daemon=False)
        _t.start()
        try:
            _t.join()
        except KeyboardInterrupt:
            print('\n[MB] 收到退出信号，关闭服务', flush=True)
            break
        if _fatal_stop:
            # 端口被占这类不可恢复的错误：别再循环刷屏，直接退出让用户看到提示
            break
        print('[WATCHDOG] 服务线程已退出，2 秒后自动重启…', flush=True)
        time.sleep(2)
    if _srv is not None:
        try: _srv.server_close()
        except Exception: pass
    return True

if __name__ == '__main__':
    serve()
