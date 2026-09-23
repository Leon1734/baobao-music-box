"""叮当预览：把当前代码的新效果截成图（同时验证壁纸皮肤）

用 Playwright 打开 player.html 并注入 window.pywebview 存根，
页面就会按"在原生窗口里"渲染 —— 截出来的图 = 用户在 exe 里看到的样子。
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://127.0.0.1:8082/player.html"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

APPSHIM = """
window.pywebview={api:{minimize(){return true},toggle_max(){window.__m=!window.__m;return window.__m},close(){return true}}};
"""


async def main():
    async with async_playwright() as pw:
        br = await pw.chromium.launch(headless=True, executable_path=CHROME,
                                      args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        pg = await br.new_page(viewport={"width": 1400, "height": 880})
        await pg.add_init_script(APPSHIM)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE, wait_until="domcontentloaded")
        await pg.wait_for_timeout(3500)

        # ① 首页（含无边框标题栏 + 窗口按钮）
        await pg.screenshot(path=os.path.join(OUT, "1_首页+无边框标题栏.png"))

        # ② 设置页 → 壁纸区
        await pg.evaluate("document.querySelector('[data-t=\"settings\"]')?.click()")
        await pg.wait_for_timeout(1200)
        await pg.evaluate("""() => {
            const g=document.getElementById('stWallGrid');
            if(g) g.scrollIntoView({block:'center'});
        }""")
        await pg.wait_for_timeout(800)
        wall_ui = await pg.evaluate("""() => {
            const g=document.getElementById('stWallGrid');
            return {items: g?g.querySelectorAll('[data-wall]').length:0,
                    sliders: !!document.getElementById('stWallDim') && !!document.getElementById('stWallBlur')};
        }""")
        await pg.screenshot(path=os.path.join(OUT, "2_设置页_壁纸选择.png"))

        # ③ 应用壁纸（水墨）→ 看整体皮肤效果
        await pg.evaluate("""() => {
            const d=document.querySelector('[data-wall="china_ink"]');
            if(d) d.click();
        }""")
        await pg.wait_for_timeout(1600)
        wp = await pg.evaluate("""() => {
            const b=document.body, cs=getComputedStyle(b,'::before');
            const rs=getComputedStyle(document.documentElement);
            return {
                hasWall: b.classList.contains('hasWall'),
                wall: rs.getPropertyValue('--wall').trim(),
                dim: rs.getPropertyValue('--wallDim').trim(),
                bgImage: cs.backgroundImage.slice(0,60),
                cardBg: getComputedStyle(document.querySelector('.card')).backgroundColor
            };
        }""")
        # 回首页看壁纸效果
        await pg.evaluate("document.querySelector('[data-t=\"home\"]')?.click()")
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=os.path.join(OUT, "3_壁纸皮肤_水墨.png"))

        # ④ 再试一张（满月）
        await pg.evaluate("""() => { const d=document.querySelector('[data-wall="myzc"]'); if(d) d.click(); }""")
        await pg.wait_for_timeout(1800)
        await pg.screenshot(path=os.path.join(OUT, "4_壁纸皮肤_满月.png"))

        # ⑤ 名画/无壁纸回退
        await pg.evaluate("""() => { const d=document.querySelector('[data-wall=""]'); if(d) d.click(); }""")
        await pg.wait_for_timeout(900)
        wp2 = await pg.evaluate("() => document.body.classList.contains('hasWall')")

        # ⑥ 歌单详情 + 返回
        await pg.evaluate("document.querySelector('[data-t=\"tj\"]')?.click()")
        await pg.wait_for_timeout(3200)
        await pg.evaluate("""() => { const it=document.querySelector('#tjG [data-tji]'); if(it) it.click(); }""")
        await pg.wait_for_timeout(3500)
        await pg.screenshot(path=os.path.join(OUT, "5_歌单详情_带返回.png"))

        # ⑦ 全屏播放页
        await pg.evaluate("document.querySelector('[data-t=\"home\"]')?.click()")
        await pg.wait_for_timeout(600)
        await pg.evaluate("""() => {
            const rows=document.querySelectorAll('#hotList .song, #recList .song, .plist .song');
            if(rows.length) rows[0].click();
        }""")
        await pg.wait_for_timeout(5000)
        await pg.evaluate("openFsLrc()")
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=os.path.join(OUT, "6_全屏播放页.png"))

        print(f"[壁纸UI] {'✅' if wall_ui['items']>=6 and wall_ui['sliders'] else '❌'} "
              f"{wall_ui['items']}个选项 滑块={wall_ui['sliders']}")
        ok = wp['hasWall'] and 'china_ink' in wp['wall'] and wp['bgImage'] != 'none'
        print(f"[壁纸生效] {'✅' if ok else '❌'} hasWall={wp['hasWall']} --wall={wp['wall']} "
              f"压暗={wp['dim']} 卡片底色={wp['cardBg']}")
        print(f"[壁纸关闭] {'✅' if not wp2 else '❌'} 回到无壁纸={not wp2}")
        print(f"[JS错误] {'✅ 无' if not errs else '❌ ' + str(errs[:1])}")
        print(f"\n截图目录: {OUT}")
        for f in sorted(os.listdir(OUT)):
            print("  " + f)
        await br.close()


if __name__ == "__main__":
    asyncio.run(main())
