"""界面改动验收：无边框标题栏 + 歌单详情视图（返回）

用 Playwright 打开 player.html，并注入一个 window.pywebview 存根，
让页面以为自己在原生窗口里 —— 这样窗口条（.winBar）会正常显示，
截图/断言拿到的就是用户在原生窗口里看到的样子。
比抢前台窗口截图可靠得多（SetForegroundWindow 常被系统拒绝）。
"""
import asyncio, sys, os
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8082/player.html"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(SHOT, exist_ok=True)

# 冒充原生窗口：让 detectBrowserMode() 不要给 body 加 isBrowser
APPSHIM = """
window.pywebview = {
  api: {
    minimize(){ window.__winCall='minimize'; return true; },
    toggle_max(){ window.__winCall='toggle_max'; window.__maxed=!window.__maxed; return window.__maxed; },
    close(){ window.__winCall='close'; return true; }
  }
};
"""


async def main():
    fails = []
    async with async_playwright() as pw:
        br = await pw.chromium.launch(headless=True,
                                      executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                      args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        pg = await br.new_page(viewport={"width": 1400, "height": 900})
        await pg.add_init_script(APPSHIM)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE, wait_until="domcontentloaded")
        await pg.wait_for_timeout(3500)

        # ── A. 无边框标题栏
        win = await pg.evaluate("""() => {
            const bar=document.getElementById('winBar');
            const da=document.getElementById('dragArea');
            const bs=['winMin','winMax','winClose'].map(i=>document.getElementById(i));
            return {
                barShown: !!bar && getComputedStyle(bar).display!=='none',
                isBrowser: document.body.classList.contains('isBrowser'),
                dragRegion: !!da && da.classList.contains('pywebview-drag-region'),
                btns: bs.map(b=>!!b),
                btnGap: (function(){const r=bs.map(b=>b?b.getBoundingClientRect():{top:-1,right:-1,left:-1,height:0});return Math.round(Math.min(...r.map(x=>x.height)))})(),
                barBg: bar?getComputedStyle(bar).backgroundColor:'',
                barBorder: bar?getComputedStyle(bar).borderTopWidth:'',
                appPadTop: getComputedStyle(document.querySelector('.app')).paddingTop,
                logoDrag: document.querySelector('.logo').classList.contains('pywebview-drag-region')
            };
        }""")
        await pg.screenshot(path=os.path.join(SHOT, "ui_1_winbar.png"),
                            clip={"x": 0, "y": 0, "width": 1400, "height": 300})

        # 点三个按钮，确认真的调到 pywebview（存根记录被调用的方法名）
        calls = []
        for bid in ("winMin", "winMax", "winClose"):
            await pg.evaluate(f"window.__winCall=null; document.getElementById('{bid}').click()")
            await pg.wait_for_timeout(250)
            calls.append(await pg.evaluate("window.__winCall"))
        win_ok = (win['barShown'] and not win['isBrowser'] and win['dragRegion']
                  and all(win['btns']) and win['barBg'] in ('rgba(0, 0, 0, 0)', 'transparent')
                  and calls == ['minimize', 'toggle_max', 'close'])
        print(f"[A] 无边框标题栏 {'✅' if win_ok else '❌'} 显示={win['barShown']} 拖拽区={win['dragRegion']} "
              f"按钮={win['btns']} 按钮高={win['btnGap']} 条背景={win['barBg']} 条边框={win['barBorder']} "
              f"logo可拖={win['logoDrag']} 顶留白={win['appPadTop']} 回调={calls}")
        if not win_ok:
            fails.append("A 无边框标题栏")

        # ── B. 推荐歌单 → 详情视图（列表隐藏 + 返回按钮）
        await pg.evaluate("document.querySelector('[data-t=\"tj\"]').click()")
        await pg.wait_for_timeout(3000)
        await pg.evaluate("document.querySelector('#tjG [data-tji]').click()")
        await pg.wait_for_timeout(3500)
        v1 = await pg.evaluate("""() => {
            const d=document.getElementById('plDC'), g=document.getElementById('tjG');
            const card=g.closest('.card');
            return {detailShown: getComputedStyle(d).display!=='none',
                    listHidden: !card || getComputedStyle(card).display==='none',
                    backBtn: !!document.querySelector('#plT .plBack'),
                    backText: (document.querySelector('#plT .plBack')||{}).textContent||'',
                    songs: document.querySelectorAll('#plS .song').length,
                    hasBackFn: typeof d.__back==='function'};
        }""")
        await pg.screenshot(path=os.path.join(SHOT, "ui_2_pl_detail.png"))
        print(f"[B] 歌单详情视图 {'✅' if (v1['detailShown'] and v1['listHidden'] and v1['backBtn'] and v1['hasBackFn']) else '❌'} "
              f"详情显示={v1['detailShown']} 列表隐藏={v1['listHidden']} 返回按钮={v1['backBtn']} "
              f"按钮文字='{v1['backText'].strip()}' 歌曲={v1['songs']}首")
        if not (v1['detailShown'] and v1['listHidden'] and v1['backBtn'] and v1['hasBackFn']):
            fails.append("B 歌单详情视图")

        # ── C. 返回：点按钮 + Esc 都要能回列表
        await pg.evaluate("document.querySelector('#plT .plBack').click()")
        await pg.wait_for_timeout(900)
        v2 = await pg.evaluate("""() => {
            const d=document.getElementById('plDC'), g=document.getElementById('tjG');
            const card=g.closest('.card');
            return {detailHidden: getComputedStyle(d).display==='none',
                    listBack: !!card && getComputedStyle(card).display!=='none',
                    gridItems: document.querySelectorAll('#tjG [data-tji]').length};
        }""")
        back_ok = v2['detailHidden'] and v2['listBack'] and v2['gridItems'] > 0
        print(f"[C] 返回按钮 {'✅' if back_ok else '❌'} 详情已隐藏={v2['detailHidden']} "
              f"列表已恢复={v2['listBack']} 歌单数={v2['gridItems']}")

        # Esc 键返回
        await pg.evaluate("document.querySelector('#tjG [data-tji]').click()")
        await pg.wait_for_timeout(3000)
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(900)
        v3 = await pg.evaluate("""() => {
            const d=document.getElementById('plDC');
            return {hidden: getComputedStyle(d).display==='none'};
        }""")
        esc_ok = v3['hidden']
        print(f"[D] Esc 返回 {'✅' if esc_ok else '❌'} 详情已隐藏={v3['hidden']}")
        if not (back_ok and esc_ok):
            fails.append("C/D 返回")

        nojs = len(errs) == 0
        print(f"[E] 无 JS 错误 {'✅' if nojs else '❌'} {errs[:2]}")
        if not nojs:
            fails.append("E JS 错误")

        await br.close()

    print("\n" + "=" * 56)
    if fails:
        print(f"❌ 未通过: {', '.join(fails)}")
    else:
        print("✅ 全部通过")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
