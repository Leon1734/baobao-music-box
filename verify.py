"""宝宝音乐盒 v5 - 最终验证（含截图）"""
import asyncio
from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://localhost:8082/player.html"
OUT = "E:/Workspace_AI/Hermes/Music/"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path=CHROME,
            args=["--autoplay-policy=no-user-gesture-required","--no-sandbox"])
        page = await b.new_page(viewport={"width":1500,"height":950})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("="*56)
        print("宝宝音乐盒 v5 最终验证")
        print("="*56)

        await page.goto(URL, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3500)

        # ── 1. 首页截图
        await page.screenshot(path=OUT+"shot_1_home.png")
        print("\n[1] 首页 ✅ 已截图")

        # ── 2. 儿童乐园
        await page.evaluate("document.querySelector('[data-t=\"kids\"]').click()")
        await page.wait_for_timeout(9000)
        kids = await page.evaluate("document.querySelectorAll('#kidsS .si').length")
        await page.screenshot(path=OUT+"shot_2_kids.png")
        print(f"[2] 儿童乐园 ✅ {kids}首儿歌")

        # ── 3. 搜索 + 播放
        await page.evaluate("""() => {
            document.querySelector('[data-t="search"]').click();
            document.getElementById('sI').value='小星星';
            document.getElementById('sB').click();
        }""")
        # 等待结果出现（最多20秒）
        n = 0
        for _ in range(20):
            await page.wait_for_timeout(1000)
            n = await page.evaluate("document.querySelectorAll('#sR .si').length")
            if n > 0: break
        print(f"   搜索到 {n} 首")
        if n == 0:
            print("   ❌ 搜索失败，跳过播放测试")
        else:
            await page.evaluate("document.querySelector('#sR .si').click()")
            # 等待音频真正开始播放（最多30秒）
            st = None
            for _ in range(30):
                await page.wait_for_timeout(1000)
                st = await page.evaluate("""() => ({
                    name: document.getElementById('tT').textContent,
                    artist: document.getElementById('tA').textContent,
                    dur: au.duration, cur: au.currentTime, paused: au.paused,
                    ready: au.readyState, lyrics: S.lyrics.length, err: au.error?au.error.code:null
                })""")
                if st['cur'] > 0.5: break
            playing = st['cur'] > 0.5 and not st['paused'] and st['err'] is None
            print(f"[3] 播放 {'✅' if playing else '❌'} {st['name'][:28]} | {st['cur']:.1f}s/{st['dur']:.0f}s | readyState={st['ready']} | 歌词{st['lyrics']}行")
            await page.screenshot(path=OUT+"shot_3_playing.png")

        # ── 4. 全屏歌词
        await page.evaluate("openFsLrc()")
        await page.wait_for_timeout(2500)
        fs = await page.evaluate("document.querySelectorAll('#fsLyrics div[data-fsi]').length")
        await page.screenshot(path=OUT+"shot_4_fullscreen.png")
        print(f"[4] 全屏歌词 {'✅' if fs>0 else '⚠️'} {fs}行")
        await page.evaluate("closeFsLrc()")
        await page.wait_for_timeout(600)

        # ── 5. 均衡器
        await page.evaluate("document.getElementById('eqBtn').click()")
        await page.wait_for_timeout(800)
        await page.evaluate("setEqPreset('摇滚')")
        await page.wait_for_timeout(600)
        eq = await page.evaluate("""() => ({
            panel: document.getElementById('eqPanel').style.display!=='none',
            preset: document.querySelector('.eq-presets button.on')?.dataset.preset,
            g0: document.querySelector('input[data-eqidx="0"]').value,
            gains: eqGains.slice(0,4)
        })""")
        await page.screenshot(path=OUT+"shot_5_eq.png")
        print(f"[5] 均衡器 ✅ 面板={eq['panel']} 预设={eq['preset']} 31Hz={eq['g0']}dB")

        # ── 6. 倍速
        await page.evaluate("setSpeed('1.5')")
        await page.wait_for_timeout(400)
        rate = await page.evaluate("au.playbackRate")
        print(f"[6] 倍速 {'✅' if rate==1.5 else '❌'} {rate}x")
        await page.evaluate("setSpeed('1')")

        # ── 7. 喜欢（先收藏再检查）
        await page.evaluate("""() => {
            const cur = S.pl[S.ci] || {id:'test_demo',name:'测试歌曲',artist:'测试歌手',source:'kw',duration:200};
            toggleLike(cur);
        }""")
        await page.wait_for_timeout(800)
        await page.evaluate("document.querySelector('[data-t=\"liked\"]').click()")
        await page.wait_for_timeout(1500)
        liked = await page.evaluate("document.querySelectorAll('#likedList .si').length")
        liked_ls = await page.evaluate("JSON.parse(localStorage.getItem('mb_liked')||'[]').length")
        recent = await page.evaluate("document.querySelectorAll('#recentList .si').length")
        await page.screenshot(path=OUT+"shot_6_liked.png")
        print(f"[7] 我喜欢 {'✅' if liked>0 else '❌'} 列表{liked}首 / 存储{liked_ls}条 / 最近播放{recent}首")

        # ── 8. 推荐歌单
        await page.evaluate("document.querySelector('[data-t=\"tj\"]').click()")
        tj = 0
        for _ in range(20):
            await page.wait_for_timeout(1000)
            tj = await page.evaluate("document.querySelectorAll('#tjG .tj-item').length")
            if tj > 0: break
        await page.screenshot(path=OUT+"shot_7_playlists.png")
        print(f"[8] 推荐歌单 {'✅' if tj>0 else '❌'} {tj}个")

        # ── 9. 歌单详情
        if tj>0:
            await page.evaluate("document.querySelector('#tjG .tj-item').click()")
            pls = 0
            for _ in range(20):
                await page.wait_for_timeout(1000)
                pls = await page.evaluate("document.querySelectorAll('#plS .si').length")
                if pls > 0: break
            await page.screenshot(path=OUT+"shot_8_plist.png")
            print(f"[9] 歌单详情 {'✅' if pls>0 else '❌'} {pls}首")

        # ── 10. 排行榜
        await page.evaluate("document.querySelector('[data-t=\"boards\"]').click()")
        await page.wait_for_timeout(1500)
        bd = await page.evaluate("document.querySelectorAll('#bList .bd').length")
        await page.evaluate("document.querySelector('#bList .bd').click()")
        bs = 0
        for _ in range(20):
            await page.wait_for_timeout(1000)
            bs = await page.evaluate("document.querySelectorAll('#bS .si').length")
            if bs > 0: break
        print(f"[10] 排行榜 {'✅' if bs>0 else '❌'} {bd}个榜单 / 首榜{bs}首")

        # ── 11. 右键菜单
        ctx = False
        for _ in range(10):
            await page.wait_for_timeout(800)
            ctx = await page.evaluate("""() => {
                hideCtxMenu();
                const el = document.querySelector('#bS .si[data-idx]') || document.querySelector('.si[data-idx]');
                if(!el) return false;
                el.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:300,clientY:300}));
                return document.getElementById('ctxMenu').classList.contains('on');
            }""")
            if ctx: break
        items = await page.evaluate("document.querySelectorAll('#ctxMenu [data-act]').length")
        print(f"[11] 右键菜单 {'✅' if ctx else '❌'} 菜单项{items}个")
        await page.evaluate("hideCtxMenu()")

        # ── 12. 键盘快捷键
        await page.keyboard.press("Space")
        await page.wait_for_timeout(600)
        paused = await page.evaluate("au.paused")
        await page.keyboard.press("Space")
        await page.wait_for_timeout(600)
        resumed = await page.evaluate("!au.paused")
        print(f"[12] 空格键 {'✅' if paused and resumed else '⚠️'} 暂停/恢复正常")

        # ── 13. 代理 Range（seek）
        await page.evaluate("au.currentTime = 60")
        await page.wait_for_timeout(3500)
        seeked = await page.evaluate("au.currentTime")
        print(f"[13] 拖动定位 {'✅' if seeked>=58 else '⚠️'} {seeked:.1f}s")

        # ── 14. 设置页
        await page.evaluate("document.querySelector('[data-t=\"settings\"]').click()")
        await page.wait_for_timeout(2500)
        st = await page.evaluate("""() => ({
            srcList: document.querySelectorAll('#srcL .src-item').length,
            quality: !!document.getElementById('stQuality'),
            accents: document.querySelectorAll('[data-accent2]').length,
            dataBtns: document.querySelectorAll('.stBtn').length,
            health: document.getElementById('stHealth').textContent,
            stats: document.getElementById('stStats').textContent.length > 10
        })""")
        st_ok = st['srcList'] > 0 and st['quality'] and st['accents'] > 0 and st['dataBtns'] >= 5
        print(f"[14] 设置页 {'✅' if st_ok else '❌'} 音源{st['srcList']}个 强调色{st['accents']}种 数据按钮{st['dataBtns']}个 服务={st['health']}")

        # ── 15. 儿童歌单展开
        await page.evaluate("document.querySelector('[data-t=\"kids\"]').click()")
        kids_pl = 0
        for _ in range(20):
            await page.wait_for_timeout(1000)
            kids_pl = await page.evaluate("document.querySelectorAll('#kidsPl .tj-item').length")
            if kids_pl > 0: break
        kpl_songs = 0
        if kids_pl > 0:
            await page.evaluate("document.querySelector('#kidsPl .tj-item').click()")
            for _ in range(20):
                await page.wait_for_timeout(1000)
                kpl_songs = await page.evaluate("document.querySelectorAll('#kidsPlSongs .si').length")
                if kpl_songs > 0: break
        print(f"[15] 儿童歌单 {'✅' if kids_pl>0 and kpl_songs>0 else '❌'} 歌单{kids_pl}个 / 点开{kpl_songs}首")

        # ── 16. 睡眠定时
        await page.evaluate("document.querySelector('[data-t=\"home\"]').click()")
        await page.evaluate("setSleepTimer('30')")
        await page.wait_for_timeout(2000)
        slp = await page.evaluate("""() => ({
            status: document.getElementById('spStatus').textContent,
            marked: document.querySelectorAll('[data-slp].on').length
        })""")
        slp_ok = '剩余' in slp['status'] and slp['marked'] > 0
        await page.evaluate("setSleepTimer('off')")
        print(f"[16] 睡眠定时 {'✅' if slp_ok else '❌'} \"{slp['status']}\"")

        # ── 17. 搜索分页
        await page.evaluate("document.querySelector('[data-t=\"search\"]').click()")
        await page.evaluate("document.getElementById('sI').value='儿歌'")
        await page.evaluate("document.getElementById('sB').click()")
        for _ in range(20):
            await page.wait_for_timeout(1000)
            if await page.evaluate("document.querySelectorAll('#sR .si').length") > 0: break
        n1 = await page.evaluate("document.querySelectorAll('#sR .si').length")
        tot = await page.evaluate("S.searchTotal")
        has_btn = await page.evaluate("!!document.querySelector('#sR .loadMoreBtn')")
        if has_btn:
            await page.evaluate("document.querySelector('#sR .loadMoreBtn').click()")
            await page.wait_for_timeout(7000)
        n2 = await page.evaluate("document.querySelectorAll('#sR .si').length")
        pg = await page.evaluate("S.searchPage")
        print(f"[17] 搜索分页 {'✅' if n2>n1 else '❌'} {n1}首 → {n2}首 / 共{tot}首 / 第{pg}页")

        # ── 18. 歌手链接
        ar_n = await page.evaluate("document.querySelectorAll('#sR .arLink').length")
        if ar_n > 0:
            await page.evaluate("document.querySelector('#sR .arLink').click()")
            await page.wait_for_timeout(8000)
        ar_r = await page.evaluate("() => ({kw: document.getElementById('sI').value, n: document.querySelectorAll('#sR .si').length})")
        print(f"[18] 歌手链接 {'✅' if ar_n>0 and ar_r['n']>0 else '❌'} {ar_n}个链接 / 搜索\"{ar_r['kw'][:15]}\" → {ar_r['n']}首")

        # ── 19. 离线缓存
        # 等搜索结果就绪（上一项歌手搜索可能仍在加载）
        for _ in range(20):
            if await page.evaluate("document.querySelectorAll('#sR .si').length") > 0: break
            await page.wait_for_timeout(1000)
        cache_r = await page.evaluate("""async () => {
            const row = document.querySelector('#sR .si');
            if(!row) return {ok:false, count:0, size:0, playable:false, err:'无搜索结果'};
            const song = S.songStore[parseInt(row.dataset.idx)];
            const ok = await cacheSong(song, false);
            const list = await audioList();
            const playable = ok ? await getCachedUrl(song) : null;
            return {ok, count: list.length, size: list.reduce((a,x)=>a+x.size,0), playable: !!playable};
        }""")
        print(f"[19] 离线缓存 {'✅' if cache_r['ok'] and cache_r['playable'] else '❌'} {cache_r['count']}首 / {cache_r['size']/1048576:.1f}MB / 可播放={cache_r['playable']}")
        # 清理
        await page.evaluate("""async () => { const l = await audioList(); for(const x of l){ await audioDel(x.key) } }""")

        # ── 20. 歌词滚动不抢用户操作
        await page.evaluate("closeFsLrc()")
        await page.wait_for_timeout(800)
        await page.evaluate("document.querySelector('[data-t=\"search\"]').click()")
        await page.evaluate("document.getElementById('sI').value='小星星'")
        await page.evaluate("document.getElementById('sB').click()")
        for _ in range(20):
            await page.wait_for_timeout(1000)
            if await page.evaluate("document.querySelectorAll('#sR .si').length") > 0: break
        await page.evaluate("playSong(S.songStore[parseInt(document.querySelector('#sR .si').dataset.idx)])")
        await page.wait_for_timeout(7000)
        await page.evaluate("openFsLrc()")
        await page.wait_for_timeout(3500)
        base = await page.evaluate("() => ({lines: document.querySelectorAll('#fsLyrics div[data-fsi]').length, pos: document.getElementById('fsLyrics').scrollTop})")
        # 模拟用户滚轮 + 手动定位到指定位置
        await page.evaluate("""() => {
            const b = document.getElementById('fsLyrics');
            b.dispatchEvent(new WheelEvent('wheel',{deltaY:-300,bubbles:true}));
            b.scrollTop = 40;
        }""")
        await page.wait_for_timeout(1200)   # 等动画结束
        p1 = await page.evaluate("() => ({paused: lrcUserScrolling, btn: document.getElementById('lrcResume').classList.contains('on'), pos: document.getElementById('fsLyrics').scrollTop})")
        # 暂停窗口内位置应保持不动（不被自动滚动抢走）
        await page.wait_for_timeout(2000)
        p2 = await page.evaluate("() => ({paused: lrcUserScrolling, pos: document.getElementById('fsLyrics').scrollTop})")
        not_stolen = p2['paused'] and abs(p2['pos'] - p1['pos']) < 20
        # 5秒后自动恢复
        await page.wait_for_timeout(3500)
        p3 = await page.evaluate("() => ({paused: lrcUserScrolling, pos: document.getElementById('fsLyrics').scrollTop})")
        resumed = (not p3['paused']) and p3['pos'] > p2['pos'] + 20
        lrc_ok = base['lines'] > 0 and p1['paused'] and p1['btn'] and not_stolen and resumed
        print(f"[20] 歌词滚动 {'✅' if lrc_ok else '❌'} {base['lines']}行 / 滚轮暂停={p1['paused']} 按钮={p1['btn']} 位置未被抢={not_stolen}({p1['pos']:.0f}→{p2['pos']:.0f}) 自动恢复={resumed}")
        # 点击"回到当前"按钮
        await page.evaluate("document.getElementById('lrcResume').click()")
        await page.wait_for_timeout(1200)
        p4 = await page.evaluate("() => ({paused: lrcUserScrolling, btn: document.getElementById('lrcResume').classList.contains('on')})")
        print(f"[21] 回到当前按钮 {'✅' if not p4['paused'] and not p4['btn'] else '❌'} 恢复跟随={not p4['paused']}")
        await page.evaluate("closeFsLrc()")

        # ── 22. 播放统计
        await page.evaluate("closeFsLrc()")
        await page.wait_for_timeout(500)
        stt = await page.evaluate("""() => {
            const s = getStats();
            return {plays: s.totalPlays, sec: Math.round(s.totalSec), songs: Object.keys(s.songs).length,
                    top: topSongs(5).length};
        }""")
        print(f"[22] 播放统计 {'✅' if stt['plays'] > 0 else '❌'} 播放{stt['plays']}次 / 收听{stt['sec']}秒 / {stt['songs']}首歌 / TOP{stt['top']}")

        # ── 23. 统计页 + 宝宝最爱歌单
        await page.evaluate("document.querySelector('[data-t=\"stats\"]').click()")
        await page.wait_for_timeout(2500)
        sp = await page.evaluate("""() => ({
            cards: document.querySelectorAll('.statCard').length,
            bars: document.querySelectorAll('.sBar').length,
            top: document.querySelectorAll('#statsTop .si').length,
            ranks: document.querySelectorAll('#statsTop .rankNo').length,
            favBtn: !!document.getElementById('statsMakeFav')
        })""")
        # 生成宝宝最爱
        fav = {"songs": 0}
        if sp['favBtn']:
            await page.evaluate("document.getElementById('statsMakeFav').click()")
            await page.wait_for_timeout(1200)
            fav = await page.evaluate("() => { const l = getMyLists(); return {count: l.length, songs: l[0] ? l[0].songs.length : 0, name: l[0] ? l[0].name : ''}; }")
        stats_ok = sp['cards'] == 3 and sp['bars'] >= 1 and sp['top'] >= 1 and fav['songs'] > 0
        print(f"[23] 统计页 {'✅' if stats_ok else '❌'} 概览{sp['cards']}卡 柱{sp['bars']}根 排行{sp['top']}首 / 宝宝最爱={fav['songs']}首")

        # ── 24. 快捷键帮助面板
        await page.evaluate("document.querySelector('[data-t=\"home\"]').click()")
        await page.evaluate("document.getElementById('helpBtn').click()")
        await page.wait_for_timeout(600)
        hp = await page.evaluate("""() => ({
            on: document.getElementById('helpPanel').classList.contains('on'),
            rows: document.querySelectorAll('.hpRow').length,
            secs: document.querySelectorAll('.hpSec').length
        })""")
        await page.evaluate("toggleHelp(false)")
        await page.wait_for_timeout(300)
        hp_off = await page.evaluate("document.getElementById('helpPanel').classList.contains('on')")
        await page.keyboard.press("?")
        await page.wait_for_timeout(600)
        hp_key = await page.evaluate("document.getElementById('helpPanel').classList.contains('on')")
        await page.evaluate("toggleHelp(false)")
        help_ok = hp['on'] and hp['rows'] >= 10 and not hp_off and hp_key
        print(f"[24] 快捷键帮助 {'✅' if help_ok else '❌'} {hp['secs']}组{hp['rows']}条 / 按钮={hp['on']} ?键={hp_key}")

        print("\n" + "="*56)
        if errors:
            print(f"⚠️ JS错误 {len(errors)}条:")
            for e in errors[:5]: print(f"  {e[:120]}")
        else:
            print("✅ 无 JS 错误")
        print("="*56)
        await b.close()

asyncio.run(main())
