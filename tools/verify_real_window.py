"""决定性验证：用**真 pywebview** 开一个与 app.py 完全相同的无边框窗口，
从窗口内部读回 DOM 状态 —— 这才是"用户到底看不看得到按钮"的唯一权威答案。

截图/PrintWindow 不可信：本机 200% DPI，抓到的是放大后的局部（实测导航栏都被截断）。

用法：  python tools/verify_real_window.py
"""
import os, sys, threading, time, json, urllib.request
os.environ["MB_PORT"] = "8083"          # 必须在 import server 之前 —— PORT 在模块顶层就读
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as mb
PORT = 8083


def _up(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception:
        return False


def main():
    port = PORT
    threading.Thread(target=mb.serve, daemon=True, name="mb-server").start()
    for _ in range(60):
        if _up(port):
            break
        time.sleep(0.2)
    else:
        print("❌ 服务起不来"); return 1

    import webview

    class _WinApi:
        def minimize(self): return "min"
        def toggle_max(self): return False
        def close(self): return "close"

    results = {}

    def run():
        time.sleep(3)          # 等页面 init + 桥注入 + 判定期
        js = r"""
        (() => {
          const g = id => { const e = document.getElementById(id); if(!e) return null;
            const s = getComputedStyle(e), r = e.getBoundingClientRect();
            return {display:s.display, w:Math.round(r.width), h:Math.round(r.height),
                    left:Math.round(r.left), top:Math.round(r.top),
                    color:s.color, bg:s.backgroundColor, opacity:s.opacity,
                    visible: s.display!=='none' && s.visibility!=='hidden'
                             && parseFloat(s.opacity)>0.05 && r.width>0 && r.height>0};
          };
          return {
            isBrowser: document.body.classList.contains('isBrowser'),
            hasBridge: !!(window.pywebview && window.pywebview.api),
            apiKeys: (window.pywebview && window.pywebview.api)
                     ? Object.keys(window.pywebview.api) : [],
            bar: g('winBar'), min: g('winMax') && g('winMin'), max: g('winMax'), close: g('winClose'),
            drag: g('dragArea'),
            dragCls: (document.getElementById('dragArea')||{}).className||'',
            innerW: window.innerWidth, innerH: window.innerHeight,
          };
        })()
        """
        results["r"] = webview.windows[0].evaluate_js(js)
        webview.windows[0].destroy()

    win = webview.create_window("宝宝音乐盒", f"http://127.0.0.1:{port}/player.html",
                                width=1307, height=825, frameless=True,
                                js_api=_WinApi(), easy_drag=False)
    webview.start(run)
    r = results.get("r")
    if not r:
        print("❌ 没读到 DOM"); return 1

    print("========== 真 pywebview 窗口内部实况 ==========")
    print(f"   窗口内尺寸   {r['innerW']} x {r['innerH']}")
    print(f"   桥已注入     {r['hasBridge']}   api={r['apiKeys']}")
    print(f"   isBrowser    {r['isBrowser']}   {'✅ 未误判' if not r['isBrowser'] else '❌ 会被隐藏'}")
    for k, label in (("bar", "标题栏"), ("min", "最小化"), ("max", "最大化"),
                     ("close", "关闭"), ("drag", "拖拽区")):
        v = r[k]
        if not v:
            print(f"   {label:6s} ❌ 元素不存在"); continue
        print(f"   {label:6s} 可见={v['visible']}  {v['w']}x{v['h']} @({v['left']},{v['top']})"
              f"  颜色={v['color']} 背景={v['bg']}")
    print(f"   拖拽标记     {r['dragCls']!r}   {'✅' if 'pywebview-drag-region' in r['dragCls'] else '❌'}")

    ok = (r["hasBridge"] and not r["isBrowser"] and r["bar"] and r["bar"]["visible"]
          and r["min"] and r["min"]["visible"] and r["max"] and r["max"]["visible"]
          and r["close"] and r["close"]["visible"]
          and "pywebview-drag-region" in r["dragCls"])
    print()
    print("✅ 真窗口里标题栏按钮齐全可见、拖拽区就位" if ok else "❌ 真窗口里仍有问题")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
