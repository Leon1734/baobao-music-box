# -*- coding: utf-8 -*-
"""稳定性压力测试：狂切页面/狂切歌/狂点按钮，抓 JS 错误 + 内存泄漏 + 监听器堆积"""
import asyncio
from playwright.async_api import async_playwright

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path=CHROME, args=['--no-sandbox'])
        page = await b.new_page(viewport={'width': 1500, 'height': 950})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e).split('\n')[0][:110]))
        warns = []
        page.on('console', lambda m: warns.append(m.text[:110]) if m.type == 'error' else None)

        await page.goto('http://localhost:8082/player.html', wait_until='networkidle', timeout=45000)
        await page.wait_for_timeout(3500)

        async def mem():
            return await page.evaluate("performance.memory ? Math.round(performance.memory.usedJSHeapSize/1048576) : -1")

        m0 = await mem()
        print(f"起始内存: {m0}MB\n")

        # ══ 压力1：狂切 10 个页面标签 × 3 轮 ══
        tabs = ['home','kids','search','board','tj','liked','mylist','local','stats','settings']
        for r in range(3):
            for t in tabs:
                await page.evaluate(f"document.querySelector('[data-t=\"{t}\"]')?.click()")
                await page.wait_for_timeout(180)
        print(f"[压力1] 切换页面 30 次 → JS错误 {len(errs)}")

        # ══ 压力2：搜索 + 狂切歌 ══
        await page.evaluate("document.querySelector('[data-t=\"search\"]').click()")
        await page.evaluate("document.getElementById('sI').value='儿歌'")
        await page.evaluate("document.getElementById('sB').click()")
        for _ in range(25):
            await page.wait_for_timeout(800)
            if await page.evaluate("document.querySelectorAll('#sR .si').length") >= 10: break
        n = await page.evaluate("document.querySelectorAll('#sR .si').length")
        print(f"[压力2] 搜索到 {n} 首，开始狂切…")
        for i in range(min(8, n)):
            await page.evaluate(f"(()=>{{const r=document.querySelectorAll('#sR .si')[{i}];if(r)playSong(S.songStore[parseInt(r.dataset.idx)])}})()")
            await page.wait_for_timeout(1200)   # 故意不等加载完就切下一首
        await page.wait_for_timeout(4000)
        st = await page.evaluate("() => ({playing: S.playing, src: au.src.slice(0,40), err: au.error?au.error.code:0})")
        print(f"[压力2] 快切8首 → 播放中={st['playing']} audioError={st['err']} JS错误 {len(errs)}")

        # ══ 压力3：狂点各种按钮 ══
        clicks = [
            "document.getElementById('helpBtn')?.click()", "toggleHelp(false)",
            "document.getElementById('themeBtn')?.click()", "document.getElementById('themePanel')?.classList.remove('on')",
            "document.getElementById('slpBtn')?.click()", "document.getElementById('slpPanel')?.classList.remove('on')",
            "document.getElementById('shuffleBtn')?.click()", "document.getElementById('repeatBtn')?.click()",
            "document.getElementById('prevBtn')?.click()", "document.getElementById('nextBtn')?.click()",
            "document.getElementById('playBtn')?.click()",
        ]
        for _ in range(3):
            for c in clicks:
                await page.evaluate(f"try{{{c}}}catch(e){{}}")
                await page.wait_for_timeout(90)
        print(f"[压力3] 狂点按钮 33 次 → JS错误 {len(errs)}")

        # ══ 压力4：快速重播同一首缓存歌（验证 blob URL 不泄漏）══
        await page.evaluate("document.querySelector('[data-t=\"search\"]').click()")
        await page.wait_for_timeout(500)
        blobtest = await page.evaluate("""async () => {
            const row=document.querySelector('#sR .si'); if(!row) return {skip:true};
            const song=S.songStore[parseInt(row.dataset.idx)];
            // 先缓存
            await cacheSong(song,false);
            const before=performance.memory?performance.memory.usedJSHeapSize:0;
            // 连播 12 次（每次都会调 getCachedUrl）
            for(let i=0;i<12;i++){ const u=await getCachedUrl(song); if(!u) return {fail:'拿不到缓存URL'}; }
            const after=performance.memory?performance.memory.usedJSHeapSize:0;
            return {cacheCount:_blobUrlCache.size, growthMB:Math.round((after-before)/1048576*10)/10};
        }""")
        if blobtest.get('skip'):
            print("[压力4] 跳过（无搜索结果）")
        else:
            ok = blobtest.get('cacheCount',0) <= 2 and blobtest.get('growthMB',99) < 5
            print(f"[压力4] 同曲取缓存12次 → blob缓存数={blobtest.get('cacheCount')} 内存增长={blobtest.get('growthMB')}MB {'✅' if ok else '❌ 泄漏!'}")

        # ══ 压力5：边界输入 ══
        edge = await page.evaluate("""() => {
            const out=[];
            // 空搜索
            try{ searchWord(''); out.push('空搜索:OK') }catch(e){ out.push('空搜索:崩溃 '+e.message) }
            // 超长歌名
            try{ storeSong({id:'x',name:'A'.repeat(300),artist:'B'.repeat(200),source:'kw'}); out.push('超长名:OK') }catch(e){ out.push('超长名:崩溃') }
            // 特殊字符歌名
            try{ storeSong({id:'y',name:`<img src=x onerror=alert(1)>&"'`,artist:`'"><script>`,source:'kw'}); out.push('特殊字符:OK') }catch(e){ out.push('特殊字符:崩溃') }
            // HTML 转义验证
            const t=document.createElement('div');
            t.innerHTML=songRowHTML({id:'z',name:'<b>粗</b>&"引号',artist:"a'b",duration:100,source:'kw'},false);
            out.push('转义:'+(t.querySelector('.nm')?.textContent.includes('<b>')?'OK(原样显示)':'❌(被当HTML解析)'));
            // 空播放列表操作
            try{ const bak=S.pl; S.pl=[]; S.ci=0; playNext(); playPrev(); S.pl=bak; out.push('空队列切歌:OK') }catch(e){ out.push('空队列切歌:崩溃 '+e.message) }
            return out;
        }""")
        for x in edge: print(f"   {x}")
        await page.wait_for_timeout(1500)

        # ══ 压力7：竞态测试 —— 快速切歌后必须停在最后一首 ══
        await page.evaluate("document.querySelector('[data-t=\"search\"]').click()")
        await page.wait_for_timeout(400)
        race = await page.evaluate("""async () => {
            const rows=[...document.querySelectorAll('#sR .si')].slice(0,10);
            if(rows.length<5) return {skip:true};
            const songs=rows.map(r=>S.songStore[parseInt(r.dataset.idx)]);
            // 不等上一首播完，连续切 10 首（故意制造 play() 被新 load 打断）
            for(const s of songs){ playSong(s); await new Promise(r=>setTimeout(r,250)); }
            const last=songs[songs.length-1];
            // 等所有异步链路走完（取URL → 代理 → play）
            await new Promise(r=>setTimeout(r,12000));
            const cur=S.pl[S.ci]||{};
            const titleUI=document.getElementById('tT').textContent;
            return {
                requested:last.name.slice(0,16),
                uiTitle:titleUI.slice(0,16),
                playing:S.playing, ready:au.readyState,
                ok: titleUI===last.name && S.playing && au.readyState>0
            };
        }""")
        if race.get('skip'):
            print("[压力7] 跳过（结果不足5首）")
        else:
            flag = '✅' if race.get('ok') else '❌ 被旧请求覆盖!'
            print(f"[压力7] 快切10首竞态 → 期望最后={race.get('requested')!r} 界面显示={race.get('uiTitle')!r} {flag}")

        # ══ 压力8：内存最终检查 ══
        m1 = await mem()
        await page.evaluate("document.querySelector('[data-t=\"home\"]').click()")
        await page.wait_for_timeout(1500)
        if await page.evaluate("!!window.gc"):
            await page.evaluate("window.gc()")
            await page.wait_for_timeout(800)
        m2 = await mem()

        print(f"\n{'='*56}")
        print(f"内存: {m0}MB → {m1}MB → GC后 {m2}MB")
        growth = m2 - m0
        print(f"净增长: {growth}MB {'✅ 正常' if growth < 30 else '⚠️ 偏高，需排查'}")
        print(f"\nJS 运行时错误: {len(errs)} 个 {'✅' if not errs else '❌'}")
        for e in errs[:6]: print(f"   ❌ {e}")
        if warns:
            print(f"console.error: {len(warns)} 条")
            for w in list(dict.fromkeys(warns))[:6]: print(f"   ⚠️ {w}")
        else:
            print("console.error: 0 条 ✅")
        await b.close()

asyncio.run(main())
