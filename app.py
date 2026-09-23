# -*- coding: utf-8 -*-
"""
宝宝音乐盒 · Windows 启动器

双击 exe 的行为：
  1. 后台启动本地音乐服务（默认 http://localhost:8082）
  2. 弹出一个**原生窗口**（Edge WebView2 内核）显示播放器 —— 不是浏览器标签页
  3. 关掉窗口即退出

设计要点：
  · 打包后 server.py / player.html 等只读资源在 PyInstaller 解包目录，
    而 photos / 音源 / config.json / 缓存 放在 exe 同级目录，用户可以直接放文件
  · 原生窗口失败（没有 WebView2 运行时）时自动退回默认浏览器，不让用户卡住
  · 服务起不来时给出可见提示（有控制台就打印，没有就弹消息框），
    绝不静默闪退
  · 端口被占 / 已有实例：直接打开那一个，不再起第二个
"""
import os
import sys
import time
import socket
import threading
import webbrowser
import traceback

# 保证能 import server（源码运行和 exe 运行都要成立）
_HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

APP_TITLE = "宝宝音乐盒"
BANNER = r"""
  宝宝音乐盒  Baobao Music Box
  -----------------------------
  本地 + 在线音乐播放器 · 家庭版
"""


# ============ 小工具 ============

def _log(msg):
    """有控制台就打印；没有（windowed 模式）就丢弃 —— 错误另有 error.log 兜底"""
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _msgbox(title, text):
    """原生消息框。windowed 模式下这是用户唯一能看到错误的地方"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _probe_app(port, timeout=1.5):
    """探测某端口上是不是宝宝音乐盒；是就返回它的 health，否则 None"""
    import json as _json
    import urllib.request as _u
    try:
        with _u.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            d = _json.loads(r.read().decode("utf-8"))
        return d if d.get("app") == "baobao-music" else None
    except Exception:
        return None


def _find_running_instance(start=8082, span=8):
    """在默认端口附近找已在运行的实例，返回 (port, health) 或 (None, None)"""
    for p in range(start, start + span * 10, 10):
        h = _probe_app(p)
        if h:
            return p, h
    return None, None


def _pick_port(start=8082, tries=8):
    """端口被占就往上找，最多试 tries 个"""
    for p in range(start, start + tries * 10, 10):
        if _port_free(p):
            return p
    return start


def _wait_ready(port, timeout=60):
    """等服务真的能响应。用 /api/health 判断，不看端口是否被占
    （别的程序占着端口也会显示「已就绪」，那会打开一个打不开的页面）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _probe_app(port, timeout=2):
            return True
        time.sleep(0.25)
    return False


# ============ 界面 ============

def _webview_available():
    """pywebview + WebView2 运行时是否可用"""
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    if os.name != "nt":
        return True
    try:
        import winreg
        key = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key) as k:
                    if winreg.QueryValueEx(k, "pv")[0]:
                        return True
            except OSError:
                pass
        return False
    except Exception:
        return True      # 检测不了就乐观一点，失败还有兜底


def _open_native_window(port):
    """原生窗口（阻塞到用户关闭窗口）。返回 True=正常关闭，False=起不来"""
    try:
        import webview
    except Exception as e:
        _log(f"[窗口] pywebview 不可用: {e}")
        return False
    url = f"http://127.0.0.1:{port}/player.html"
    try:
        webview.create_window(
            APP_TITLE, url,
            width=1320, height=860,
            min_size=(960, 620),
            background_color="#0f0f16",
            text_select=False,
            confirm_close=False,
        )
        webview.start()          # 阻塞直到窗口关闭
        return True
    except Exception as e:
        _log(f"[窗口] 原生窗口启动失败: {type(e).__name__}: {e}")
        return False


def _open_ui(port, use_browser=False, block=True):
    """开界面：优先原生窗口，失败退回浏览器"""
    url = f"http://localhost:{port}/player.html"
    if not use_browser and _webview_available():
        if _open_native_window(port):
            return
        _log("[窗口] 退回默认浏览器模式")
    try:
        webbrowser.open(url)
    except Exception:
        _log(f"[提示] 请手动打开：{url}")
    if block:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


# ============ 参数 ============

class Args:
    def __init__(self):
        self.port = None          # type: int | None
        self.browser = False
        self.help = False


def _parse_args(argv):
    a = Args()
    i = 0
    while i < len(argv):
        t = argv[i]
        if t in ("-p", "--port") and i + 1 < len(argv):
            try:
                a.port = int(argv[i + 1]); i += 2; continue
            except ValueError:
                _msgbox(APP_TITLE, f"端口必须是数字：{argv[i + 1]}")
                return None
        elif t.startswith("--port="):
            try:
                a.port = int(t.split("=", 1)[1])
            except ValueError:
                _msgbox(APP_TITLE, f"端口必须是数字：{t}")
                return None
        elif t in ("-b", "--browser", "--no-window"):
            a.browser = True
        elif t in ("-h", "--help", "/?"):
            a.help = True
        i += 1
    return a


HELP_TEXT = f"""{BANNER}
  用法:  宝宝音乐盒.exe [选项]

    -p, --port N       指定端口（默认 8082，被占用则往上找）
    -h, --help         显示本帮助

  也可以用环境变量 MB_PORT 指定端口。

  数据目录（照片/音源/缓存）就在 exe 旁边：
    photos\\     放你自己的照片
    音源\\       放你自己的音源 .js
    config.json 音源密钥（一般不需要）
"""


# ============ 主流程 ============

def main():
    _log(BANNER)
    args = _parse_args(sys.argv[1:])
    if args is None:
        return 1
    if args.help:
        _log(HELP_TEXT)
        # windowed 模式下控制台不可见，用消息框显示帮助
        if not sys.stdout or not sys.stdout.isatty():
            _msgbox(APP_TITLE, HELP_TEXT)
        return 0

    # 已经有实例在跑？直接把界面打开到它，不再起第二个
    if not args.port and not os.environ.get('MB_PORT'):
        rp, rh = _find_running_instance()
        if rp:
            _log(f"[提示] 宝宝音乐盒已经在运行了（端口 {rp}），直接打开它。")
            _log(f"       它的数据目录：{(rh or {}).get('data_dir')}")
            _open_ui(rp, use_browser=args.browser, block=False)
            return 0

    try:
        import server
    except Exception:
        _log("[错误] 无法加载服务模块 server.py：")
        traceback.print_exc()
        _msgbox(APP_TITLE, "无法加载服务模块 server.py：\n\n" + traceback.format_exc()[-1200:])
        return 1

    # 端口优先级：命令行 --port > 环境变量 MB_PORT > 自动挑（8082 起）
    port = args.port or int(os.environ.get('MB_PORT', 0)) or _pick_port(8082)
    server.PORT = port
    os.environ['MB_PORT'] = str(port)

    _log(f"  访问地址: http://localhost:{port}/player.html")
    _log(f"  数据目录: {server.DATA_DIR}")

    # 后台线程起服务（pywebview 的 start() 必须占用主线程）
    threading.Thread(target=server.serve, daemon=True, name="mb-server").start()

    if not _wait_ready(port, timeout=60):
        detail = (f"服务没能在 60 秒内启动（端口 {port}）。\n\n"
                  f"常见原因：\n"
                  f"  · 端口被别的程序占用 → 换个端口试试\n"
                  f"    命令行：宝宝音乐盒.exe --port 9000\n"
                  f"  · 杀毒软件拦截了本地监听\n\n"
                  f"数据目录：{server.DATA_DIR}")
        elog = getattr(server, "ERROR_LOG", None)
        if elog and os.path.exists(elog):
            try:
                detail += "\n\n最近错误日志：\n" + open(elog, encoding="utf-8", errors="replace").read()[-800:]
            except Exception:
                pass
        _log("[错误] " + detail)
        _msgbox(APP_TITLE, detail)
        return 1

    _log("  启动完成。关闭窗口即退出。")
    _log("=" * 46)
    _open_ui(port, use_browser=args.browser)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        _msgbox(APP_TITLE, "程序异常退出：\n\n" + traceback.format_exc()[-1500:])
        raise
