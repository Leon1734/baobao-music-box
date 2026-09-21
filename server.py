"""
宝宝音乐盒 v3 - 完整版
HYW音源API直接调用 + 酷我API + 本地文件
"""
import http.server, socketserver, os, json, urllib.parse, urllib.request, ssl, threading, time
from pathlib import Path

PORT = int(os.environ.get('MB_PORT', 8082))   # 可用环境变量换端口，避免多实例端口冲突
BASE = Path(__file__).parent
PHOTOS = BASE / "photos"
SOURCES = BASE / "音源"
KIDS_CACHE_FILE = BASE / "kids_cache.json"

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


# HYW音源API配置 (从HYWmusic_beta_公益测试 v0.74.0.js提取)
HYW_API = "http://103.79.184.97"
HYW_KEY = "REDACTED-KEY-REMOVED"

socketserver.TCPServer.allow_reuse_address = True
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(BASE), **kw)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(p.path)
        Q = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
        try:
            if path == '/api/photos': return self.j(self._photos())
            if path == '/api/music': return self.j(self._local_music())
            if path == '/api/sources': return self.j(self._sources())
            if path == '/api/search': return self.j(self._search(Q.get('keyword',''), Q.get('source','kw'), int(Q.get('limit','30'))))
            if path == '/api/url': return self.j(self._get_url(Q))
            if path == '/api/lyric': return self.j(self._get_lyric(Q))
            if path == '/api/pic': return self.j(self._get_pic(Q))
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
            return self.j({'error': str(e)})
        super().do_GET()

    def j(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type','application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _get(self, url, headers=None):
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        if headers:
            for k,v in headers.items(): req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            print(f"[HTTP] {url} -> {e}")
            return None

    # ====== 照片 ======
    # 优先返回 photos_web/ 下的压缩版（tools/make_photos_web.py 生成，单张 ~20MB -> ~200KB），
    # 无压缩版时自动回退原图；网页端无需任何改动（均通过 /api/photos 取图）
    def _photos(self):
        if not PHOTOS.exists(): return []
        web = BASE / 'photos_web'
        out = []
        for f in sorted(PHOTOS.iterdir()):
            if f.suffix.lower() not in ('.jpg','.jpeg','.png','.gif','.webp'): continue
            if (web / (f.stem + '.jpg')).exists():
                out.append({'name': f.stem, 'url': '/photos_web/' + urllib.parse.quote(f.stem + '.jpg')})
            else:
                out.append({'name': f.stem, 'url': '/photos/' + urllib.parse.quote(f.name)})
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
        if not SOURCES.exists(): return []
        return [{'name':f.stem,'size':f.stat().st_size}
                for f in sorted(SOURCES.iterdir())
                if f.is_file() and f.suffix=='.js' and f.stat().st_size > 1000]

    # ====== 在线搜索 (酷我) ======
    def _search(self, kw, src='kw', limit=30):
        if not kw: return {'songs':[],'total':0}
        if src == 'kw':
            url = f'http://search.kuwo.cn/r.s?client=kt&all={urllib.parse.quote(kw)}&pn=0&rn={limit}&uid=794762570&ver=kwplayer_ar_9.2.2.1&vipver=1&show_copyright_off=1&newver=1&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vermerge=1&mobi=1&issubtitle=1'
            d = self._get(url)
            if d and d.get('abslist'):
                songs = []
                for s in d['abslist']:
                    mid = s.get('MUSICRID','').replace('MUSIC_','')
                    if not mid: continue
                    songs.append({'id':mid,'songmid':mid,'name':s.get('SONGNAME',''),'artist':s.get('ARTIST',''),'album':s.get('ALBUM',''),'duration':int(s.get('DURATION',0)),'source':'kw'})
                return {'songs':songs,'total':int(d.get('TOTAL',0)),'source':'kw'}
        elif src == 'wy':
            url = f'https://music.163.com/api/search/get/web?s={urllib.parse.quote(kw)}&type=1&offset=0&limit={limit}'
            d = self._get(url, {'Referer':'https://music.163.com/'})
            if d and d.get('result') and d['result'].get('songs'):
                songs = [{'id':str(s['id']),'songmid':str(s['id']),'name':s['name'],
                          'artist':'/'.join([a['name'] for a in s.get('artists',[])]),
                          'album':s.get('album',{}).get('name',''),'duration':s.get('duration',0)//1000,'source':'wy'}
                         for s in d['result']['songs']]
                return {'songs':songs,'total':d['result'].get('songCount',0),'source':'wy'}
        return {'songs':[],'total':0,'source':src}

    # ====== HYW音源获取播放URL ======
    def _get_url(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        name = Q.get('name','')
        artist = Q.get('artist','')

        # 方式1: 通过HYW音源API
        params = {'songId': sid, 'source': src, 'key': HYW_KEY, 'quality': '320k'}
        if name: params['name'] = name
        if artist: params['artist'] = artist
        query = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k,v in params.items() if v)
        url = f'{HYW_API}/api/music/url?{query}'
        d = self._get(url)
        if d and d.get('code') == 200:
            result = d.get('url') or d.get('data') or ''
            if isinstance(result, str) and result.startswith('http'):
                return {'url': result, 'source': 'hyw'}
            elif isinstance(result, dict) and result.get('url'):
                return {'url': result['url'], 'source': 'hyw'}

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

        return {'error': '无法获取播放链接'}

    # ====== 歌词 ======
    def _get_lyric(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        if src == 'kw':
            d = self._get(f'http://m.kuwo.cn/newh5/singles/songinfoandlrc?musicId={sid}')
            if d and d.get('status')==200 and d.get('data') and d['data'].get('lrclist'):
                lines = []
                for l in d['data']['lrclist']:
                    t = float(l.get('time',0))
                    txt = l.get('lineLyric','')
                    if txt: lines.append(f'[{int(t//60):02d}:{t%60:05.2f}]{txt}')
                return {'lyric':'\n'.join(lines)}
        if src == 'wy':
            d = self._get(f'https://music.163.com/api/song/lyric?id={sid}&lv=1', {'Referer':'https://music.163.com/'})
            if d and d.get('lrc') and d['lrc'].get('lyric'):
                return {'lyric': d['lrc']['lyric']}
        return {'lyric':''}

    # ====== 封面 ======
    def _get_pic(self, Q):
        sid = Q.get('id','')
        src = Q.get('source','kw')
        if src == 'kw':
            return {'url': f'http://artistpicserver.kuwo.cn/pic.web?type=rid_pic&pictype=500&size=500&rid={sid}'}
        if src == 'wy':
            d = self._get(f'https://music.163.com/api/song/detail?id={sid}&ids=[{sid}]', {'Referer':'https://music.163.com/'})
            if d and d.get('songs') and d['songs'][0].get('album',{}).get('picUrl'):
                return {'url': d['songs'][0]['album']['picUrl']}
        return {'url': ''}

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
        return {'ok': True, 'port': PORT, 'photos': len(self._photos()), 'local_songs': len(self._local_music()),
                'kids_sections': len(_kids_state['data'] or []),
                'kids_age_s': int(time.time() - _kids_state['ts']) if _kids_state['ts'] else None,
                'kids_cache_file': KIDS_CACHE_FILE.exists()}

    # ====== 音频代理 (解决CORS问题) ======
    def _proxy(self, url):
        if not url or not url.startswith('http'):
            return self.j({'error': 'invalid url'})
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                content_type = r.headers.get('Content-Type', 'audio/mpeg')
                data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def log_message(self, fmt, *args):
        msg = str(args[0]) if args else ''
        if not any(x in msg for x in ('.css','.woff','.ttf','.ico','.png','.jpg','.gif')):
            print(f"[MB] {msg}")

if __name__ == '__main__':
    os.chdir(str(BASE))
    with socketserver.ThreadingTCPServer(("", PORT), H) as httpd:
        print(f"宝宝音乐盒 v3 启动! http://localhost:{PORT}/player.html")
        httpd.serve_forever()
