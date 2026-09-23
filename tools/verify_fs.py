"""验收 #2：全屏页的播放列表抽屉 + 6 种样式频谱可视化

关键点：频谱要有真实音频数据才会跳，所以先播一首歌再采样 canvas 像素。
判据 = canvas 上真的画出了东西（非透明像素数 > 阈值），而不只是"元素存在"。
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://127.0.0.1:8082/player.html"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

APPSHIM = "window.pywebview={api:{minimize(){return true},toggle_max(){return true},close(){return true}}};"

# 采样 canvas：数非透明像素，判断"真的画出来了"
PAINTED = """() => {
  const cv=document.getElementById('fsViz');
  if(!cv) return {ok:false,n:0};
  const c=cv.getContext('2d');
  const d=c.getImageData(0,0,cv.width,cv.height).data;
  let n=0;
  for(let i=3;i<d.length;i+=4) if(d[i]>8) n++;
  return {ok:n>0, n:n, w:cv.width, h:cv.height, px:d.length/4};
}"""


async def main():
    fails = []
    async with async_playwright() as pw:
        br = await pw.chromium.launch(headless=True, executable_path=CHROME,
                                      args=["--autoplay-policy=no-user-gesture-required",
                                            "--no-sandbox", "--mute-audio"])
        pg = await br.new_page(viewport={"width": 1440, "height": 900})
        await pg.add_init_script(APPSHIM)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE, wait_until="domcontentloaded")
        await pg.wait_for_timeout(3500)

        # ── 1. 播一首歌（频谱要有音频喂数据）
        played = await pg.evaluate("""async () => {
            // 优先用队列里已有的，没有就搜一首
            if(!S.pl.length){
                const r=await fetch(A+'/api/search?keyword='+encodeURIComponent('小星星')+'&source=all&limit=6&page=1');
                const d=await r.json();
                if(d.songs&&d.songs.length){ S.pl=d.songs.slice(0,6); renderPlaylist(); }
            }
            if(!S.pl.length) return 'no-songs';
            playSong(S.pl[0]);
            return 'ok:'+S.pl.length;
        }""")
        print(f"[1] 播放准备 {'✅' if str(played).startswith('ok:') else '❌'} {played}")
        if not str(played).startswith("ok:"):
            fails.append("1 播放准备")
        await pg.wait_for_timeout(6000)

        now = await pg.evaluate("() => ({paused:au.paused, t:au.currentTime||0, dur:au.duration||0, ci:S.ci, n:S.pl.length})")
        print(f"    播放中: paused={now['paused']} {now['t']:.1f}/{now['dur']:.1f}s 队列{now['n']}首 当前#{now['ci']+1}")

        # ── 2. 进全屏，检查底部结构与样式选项
        await pg.evaluate("openFsLrc()")
        await pg.wait_for_timeout(3500)   # 等 analyser 建好 + 画几帧
        ui = await pg.evaluate("""() => {
            const sel=document.getElementById('fsVizStyle');
            const opts=sel?[...sel.options].map(o=>o.value):[];
            const q=document.getElementById('fsQueue');
            return {
                viz: !!document.getElementById('fsViz'),
                styles: opts,
                selVal: sel?sel.value:null,
                qBtn: !!document.getElementById('fsQBtn'),
                qDrawer: !!q,
                qClosed: q?!q.classList.contains('on'):false,
                qNum: (document.getElementById('fsQNum')||{}).textContent||'0',
                analyser: typeof analyser!=='undefined' && !!analyser,
                vizRAF: typeof vizRAF!=='undefined' && !!vizRAF
            };
        }""")
        want = ["bars", "mirror", "peak", "wave", "dots", "circle"]
        print(f"[2] 全屏底部结构 {'✅' if ui['viz'] and ui['qBtn'] and ui['qDrawer'] and ui['styles']==want else '❌'} "
              f"画布={ui['viz']} 列表按钮={ui['qBtn']} 抽屉={ui['qDrawer']} 样式={ui['styles']}")
        print(f"    analyser={ui['analyser']} RAF运行={ui['vizRAF']} 队列计数={ui['qNum']} 抽屉初始关闭={ui['qClosed']}")

        # ── 3. 逐个样式采样，确认都在真的绘制
        results = {}
        for st in want:
            await pg.evaluate(f"setVizStyle('{st}')")
            await pg.wait_for_timeout(900)
            r = await pg.evaluate(PAINTED)
            results[st] = r['n']
        alive = {k: v for k, v in results.items() if v > 200}
        all_draw = len(alive) == len(want)
        print(f"[3] 6 种样式绘制 {'✅' if all_draw else '❌'} " +
              " ".join(f"{k}={results[k]}" for k in want))
        if not all_draw:
            fails.append("3 频谱样式绘制")
        # 截图：挑一个好看的样式
        await pg.evaluate("setVizStyle('bars')")
        await pg.wait_for_timeout(1200)
        await pg.screenshot(path=os.path.join(OUT, "fs_1_频谱柱状.png"))

        # ── 4. 播放列表抽屉
        await pg.evaluate("document.getElementById('fsQBtn').click()")
        await pg.wait_for_timeout(900)
        d1 = await pg.evaluate("""() => {
            const q=document.getElementById('fsQueue');
            const items=[...q.querySelectorAll('.fsQItem')];
            return {open:q.classList.contains('on'),
                    items:items.length,
                    curIdx:items.findIndex(e=>e.classList.contains('on')),
                    firstName:(items[0]||{}).textContent||'',
                    cur: S.ci};
        }""")
        drawer_ok = d1['open'] and d1['items'] == now['n'] and d1['curIdx'] == d1['cur']
        print(f"[4] 播放列表抽屉 {'✅' if drawer_ok else '❌'} 打开={d1['open']} 列出{d1['items']}首 "
              f"高亮第{d1['curIdx']+1}首(应为{d1['cur']+1})")
        if not drawer_ok:
            fails.append("4 抽屉")
        await pg.screenshot(path=os.path.join(OUT, "fs_2_播放列表抽屉.png"))

        # ── 5. 点抽屉里的第 3 首，应切歌
        if d1['items'] >= 3:
            await pg.evaluate("document.querySelectorAll('#fsQueue .fsQItem')[2].click()")
            await pg.wait_for_timeout(2800)
            d2 = await pg.evaluate("() => ({ci:S.ci, hi:[...document.querySelectorAll('#fsQueue .fsQItem')].findIndex(e=>e.classList.contains('on'))})")
            pick_ok = d2['ci'] == 2 and d2['hi'] == 2
            print(f"[5] 点列表切歌 {'✅' if pick_ok else '❌'} 当前=S.ci={d2['ci']} 抽屉高亮={d2['hi']}")
            if not pick_ok:
                fails.append("5 点列表切歌")
        else:
            print("[5] 点列表切歌 ⏭ 队列不足 3 首，跳过")

        # ── 6. Esc 先收抽屉、再关全屏
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(700)
        e1 = await pg.evaluate("() => ({drawer:document.getElementById('fsQueue').classList.contains('on'), fs:document.getElementById('fsLrc').classList.contains('on')})")
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(700)
        e2 = await pg.evaluate("() => ({drawer:document.getElementById('fsQueue').classList.contains('on'), fs:document.getElementById('fsLrc').classList.contains('on')})")
        esc_ok = e1['drawer'] is False and e1['fs'] is True and e2['fs'] is False
        print(f"[6] Esc 分级关闭 {'✅' if esc_ok else '❌'} 第一次→抽屉={e1['drawer']}/全屏={e1['fs']}  第二次→全屏={e2['fs']}")
        if not esc_ok:
            fails.append("6 Esc 分级")

        # ── 7. 样式持久化
        await pg.evaluate("setVizStyle('circle')")
        await pg.wait_for_timeout(400)
        await pg.reload(wait_until="domcontentloaded")
        await pg.wait_for_timeout(3000)
        saved = await pg.evaluate("() => ({ls:localStorage.getItem('mb_viz_style'), cur:vizStyle, sel:document.getElementById('fsVizStyle').value})")
        persist_ok = saved['ls'] == 'circle' and saved['cur'] == 'circle' and saved['sel'] == 'circle'
        print(f"[7] 样式记忆 {'✅' if persist_ok else '❌'} localStorage={saved['ls']} 变量={saved['cur']} 下拉={saved['sel']}")
        if not persist_ok:
            fails.append("7 样式记忆")

        nojs = len(errs) == 0
        print(f"[8] 无 JS 错误 {'✅' if nojs else '❌'} {errs[:2]}")
        if not nojs:
            fails.append("8 JS错误")
        await br.close()

    print("\n" + "=" * 56)
    print("✅ 全部通过" if not fails else f"❌ 未通过: {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
