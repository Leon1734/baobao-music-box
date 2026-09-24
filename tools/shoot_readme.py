"""产出 README 配图到 docs/images/（这套要入库，区别于 gitignore 的 docs/screenshots/ 开发产物）。

每张图都是功能的真实界面，不是示意图。用 Playwright 本地 Chrome 渲染，
尺寸固定 1600x1000，PNG 压缩后入库。
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images")
URL = "http://localhost:8082/player.html"
W, H = 1600, 1000
os.makedirs(OUT, exist_ok=True)

# 说明文字一并输出，方便 README 对照
SHOTS = [
    ("01-home",     "home",    "首页 · 宝宝相册轮播 + 儿歌快捷入口"),
    ("02-search",   "search",  "在线搜索 · 四平台聚合检索，跨源换源兜底"),
    ("03-boards",   "boards",  "排行榜 · 137 个榜单按平台 Tab 切换"),
    ("04-playlists","playlists","我的歌单 · 点开进入歌单详情页，可返回"),
    ("05-kids",     "kids",    "儿童乐园 · 儿歌专区"),
    ("06-stats",    "stats",   "统计 · 收听数据"),
    ("07-settings", "settings","设置 · 本地音乐/音源管理"),
]


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True, executable_path=CHROME,
                                     args=["--autoplay-policy=no-user-gesture-required",
                                           "--no-sandbox"])
        ctx = await br.new_context(viewport={"width": W, "height": H},
                                   device_scale_factor=1)
        pg = await ctx.new_page()
        await pg.add_init_script("""
          Object.defineProperty(window,'pywebview',{value:{api:{
            minimize:()=>Promise.resolve(), toggle_max:()=>Promise.resolve(false),
            close:()=>Promise.resolve(),
          }},configurable:true});
        """)
        await pg.goto(URL, wait_until="networkidle")
        await pg.wait_for_timeout(3500)

        made = []
        for name, tab, desc in SHOTS:
            try:
                if tab != "home":
                    await pg.click(f'.tab[data-t="{tab}"]', timeout=6000)
                    await pg.wait_for_timeout(2600)   # 等接口出数
                shot = os.path.join(OUT, f"{name}.png")
                await pg.screenshot(path=shot)
                sz = os.path.getsize(shot)
                made.append((name, desc, sz))
                print(f"  ✅ {name}.png  {sz//1024} KB   {desc}")
            except Exception as e:
                print(f"  ❌ {name}: {e}")

        # 全屏播放页（键盘 F）—— 播放页相册 + 歌词 + 频谱
        try:
            await pg.keyboard.press("f")
            await pg.wait_for_timeout(1800)
            shot = os.path.join(OUT, "08-player.png")
            await pg.screenshot(path=shot)
            made.append(("08-player", "全屏播放页 · 歌词 + 频谱可视化 + 播放队列", os.path.getsize(shot)))
            print(f"  ✅ 08-player.png  {os.path.getsize(shot)//1024} KB   全屏播放页")
            # 频谱样式切换按钮
            try:
                await pg.click("#fsVizStyleBtn", timeout=3000)
                await pg.wait_for_timeout(900)
                shot = os.path.join(OUT, "09-viz.png")
                await pg.screenshot(path=shot)
                made.append(("09-viz", "频谱可视化 · 6 种样式可选", os.path.getsize(shot)))
                print(f"  ✅ 09-viz.png  {os.path.getsize(shot)//1024} KB")
            except Exception:
                pass
            # 队列抽屉（键盘 Q）
            await pg.keyboard.press("q")
            await pg.wait_for_timeout(900)
            shot = os.path.join(OUT, "10-queue.png")
            await pg.screenshot(path=shot)
            made.append(("10-queue", "播放队列抽屉", os.path.getsize(shot)))
            print(f"  ✅ 10-queue.png  {os.path.getsize(shot)//1024} KB")
        except Exception as e:
            print(f"  ❌ 全屏播放页: {e}")

        # 壁纸皮肤
        try:
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(600)
            await pg.click('button[title*="皮肤"], button[title*="主题"], #themeBtn', timeout=4000)
            await pg.wait_for_timeout(1500)
            shot = os.path.join(OUT, "11-wallpapers.png")
            await pg.screenshot(path=shot)
            made.append(("11-wallpapers", "皮肤 · 壁纸选择", os.path.getsize(shot)))
            print(f"  ✅ 11-wallpapers.png  {os.path.getsize(shot)//1024} KB")
        except Exception as e:
            print(f"  ⚠️ 壁纸页跳过: {e}")

        await br.close()

    total = sum(s for _, _, s in made)
    print(f"\n共 {len(made)} 张，合计 {total//1024} KB → docs/images/")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
