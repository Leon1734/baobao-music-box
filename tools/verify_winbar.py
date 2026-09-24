"""验证无边框窗口的标题栏 —— 用户反馈"不能拖动窗口、没有最小化最大化关闭按钮"。

要测的是**渲染可见性**，不是 DOM 里存不存在（verify_ui 只断言存在，所以漏了这个 bug）：
  ① 原生窗口模式（有 window.pywebview.api）→ 标题栏必须显示，三个按钮必须可见
  ② 浏览器模式（无桥）              → 3 秒后应隐藏标题栏
  ③ 两种模式都截图，肉眼可核对
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SHOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "screenshots")
URL = "http://localhost:8082/player.html"
os.makedirs(SHOT, exist_ok=True)

# 模拟 pywebview 注入的桥（真实 app 里 window.pywebview.api.minimize 等存在）
STUB = """
Object.defineProperty(window,'pywebview',{value:{api:{
  minimize:()=>{window.__winCalls.push('minimize');return Promise.resolve()},
  toggle_max:()=>{window.__winCalls.push('toggle_max');return Promise.resolve(false)},
  close:()=>{window.__winCalls.push('close');return Promise.resolve()},
}},configurable:true});
window.__winCalls=[];
document.dispatchEvent(new Event('pywebviewready'));
"""

PROBE = """
(() => {
  const bar=document.getElementById('winBar');
  const cs=bar?getComputedStyle(bar):null;
  const vis=el=>{ if(!el) return null;
    const s=getComputedStyle(el), r=el.getBoundingClientRect();
    return {display:s.display, opacity:s.opacity, visibility:s.visibility,
            w:Math.round(r.width), h:Math.round(r.height), top:Math.round(r.top),
            color:s.color, bg:s.backgroundColor, visible:
              s.display!=='none' && s.visibility!=='hidden' && parseFloat(s.opacity)>0.05
              && r.width>0 && r.height>0};
  };
  return {
    isBrowser: document.body.classList.contains('isBrowser'),
    bar: vis(bar),
    min: vis(document.getElementById('winMin')),
    max: vis(document.getElementById('winMax')),
    close: vis(document.getElementById('winClose')),
    drag: vis(document.getElementById('dragArea')),
    dragCls: (document.getElementById('dragArea')||{}).className||'',
    appPadTop: getComputedStyle(document.querySelector('.app')).paddingTop,
  };
})()
"""


async def main():
    os.makedirs(SHOT, exist_ok=True)
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True, executable_path=CHROME,
                                     args=["--autoplay-policy=no-user-gesture-required",
                                           "--no-sandbox"])
        print("========== 无边框标题栏验证 ==========")

        # ---------- ① 原生窗口模式 ----------
        ctx = await br.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        await pg.add_init_script(STUB)
        await pg.goto(URL, wait_until="networkidle")
        await pg.wait_for_timeout(4500)        # 比 3s 判定期更长
        r = await pg.evaluate(PROBE)
        print(f"\n① 原生窗口模式（模拟 pywebview 宿主）")
        print(f"   isBrowser 误加 = {r['isBrowser']}   {'✅ 未误判' if not r['isBrowser'] else '❌ 被误判成浏览器 → 标题栏被隐藏'}")
        print(f"   标题栏  可见={r['bar']['visible']}  高={r['bar']['h']}px  底色={r['bar']['bg']}")
        for k, label in (("min", "最小化"), ("max", "最大化"), ("close", "关闭")):
            v = r[k]
            print(f"   {label:6s} 可见={v['visible']}  {v['w']}x{v['h']}  颜色={v['color']}  背景={v['bg']}")
        print(f"   拖拽区  class='{r['dragCls']}'  宽={r['drag']['w']}px  {'✅ 含 pywebview-drag-region' if 'pywebview-drag-region' in r['dragCls'] else '❌ 缺拖拽标记'}")
        print(f"   .app 顶部留白 = {r['appPadTop']}   {'✅ 给标题栏让位' if r['appPadTop'] in ('42px',) else '⚠️'}")
        # 点按钮，确认真的调到了桥
        calls = await pg.evaluate("""(async()=>{
            window.__winCalls=[];
            document.getElementById('winMin').click();
            document.getElementById('winMax').click();
            document.getElementById('winClose').click();
            await new Promise(r=>setTimeout(r,300));
            return window.__winCalls;
        })()""")
        print(f"   点击回调   = {calls}   {'✅ 三个按钮都调到了窗口桥' if calls==['minimize','toggle_max','close'] else '❌ 没调通'}")
        shot1 = os.path.join(SHOT, "winbar_1_native.png")
        await pg.screenshot(path=shot1, clip={"x": 0, "y": 0, "width": 1440, "height": 130})
        ok1 = (not r["isBrowser"] and r["bar"]["visible"] and r["min"]["visible"]
               and r["max"]["visible"] and r["close"]["visible"]
               and "pywebview-drag-region" in r["dragCls"]
               and calls == ["minimize", "toggle_max", "close"])
        await ctx.close()

        # ---------- ② 浏览器模式 ----------
        ctx2 = await br.new_context(viewport={"width": 1440, "height": 900})
        pg2 = await ctx2.new_page()
        await pg2.goto(URL, wait_until="networkidle")
        await pg2.wait_for_timeout(4500)       # 等过 3s 判定期
        r2 = await pg2.evaluate(PROBE)
        print(f"\n② 浏览器模式（无 pywebview 桥）")
        print(f"   isBrowser 已加 = {r2['isBrowser']}   {'✅ 正确隐藏' if r2['isBrowser'] else '⚠️ 未隐藏（浏览器里会多一条无用标题栏）'}")
        print(f"   标题栏  可见={r2['bar']['visible']}   {'✅ 已隐藏' if not r2['bar']['visible'] else '⚠️ 仍在显示'}")
        shot2 = os.path.join(SHOT, "winbar_2_browser.png")
        await pg2.screenshot(path=shot2, clip={"x": 0, "y": 0, "width": 1440, "height": 130})
        ok2 = (r2["isBrowser"] and not r2["bar"]["visible"])
        await ctx2.close()
        await br.close()

        print(f"\n   截图: {shot1}")
        print(f"         {shot2}")
        print()
        if ok1 and ok2:
            print("✅ 两种模式都正确：原生窗口有标题栏可拖可关，浏览器里自动隐藏")
        elif ok1:
            print("✅ 核心问题已修复（原生窗口标题栏可用）；浏览器模式未隐藏，属次要")
        else:
            print("❌ 标题栏仍有问题")
        return 0 if ok1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
