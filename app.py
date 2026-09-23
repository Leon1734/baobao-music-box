# -*- coding: utf-8 -*-
"""
宝宝音乐盒 · 一键启动器（Windows 免安装版入口）

双击 exe 就会：
  1. 启动本地音乐服务（默认 http://localhost:8082）
  2. 自动打开默认浏览器
  3. 关掉控制台窗口即停止服务

设计要点：
  · 打包后 server.py / player.html 等只读资源在 PyInstaller 解包目录，
    而 photos / 音源 / config.json / 缓存 放在 exe 同级目录，用户可以直接放文件
  · 端口被占时自动往上找可用端口（8082 → 8092）
  · 服务起不来时把错误留在窗口里，不让用户对着闪退的黑框猜
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

BANNER = r"""
  宝宝音乐盒  Baobao Music Box
  -----------------------------
  本地 + 在线音乐播放器 · 家庭版
"""


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


def _wait_and_open(port, timeout=45):
    """等服务真的能响应了再开浏览器。

    原来用「端口是否被占」判断就绪 —— 在 Windows 上不可靠：
    另一个实例（或别的程序）占着端口时也会显示「已就绪」，
    而自己的服务其实没起来。改为直接问 /api/health，拿到 app 标识才算就绪。
    """
    import json as _json
    import urllib.request as _u
    t0 = time.time()
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() - t0 < timeout:
        try:
            with _u.urlopen(url, timeout=2) as r:
                d = _json.loads(r.read().decode("utf-8"))
            if d.get("app") == "baobao-music":
                time.sleep(0.2)
                try:
                    webbrowser.open(f"http://localhost:{port}/player.html")
                except Exception:
                    pass
                return
        except Exception:
            pass
        time.sleep(0.3)
    print(f"[警告] 服务在 {timeout} 秒内没有就绪。", flush=True)
    print(f"       请手动打开：http://localhost:{port}/player.html", flush=True)
    print(f"       若仍打不开，试试换端口：宝宝音乐盒.exe --port 9000", flush=True)


def _pause_if_launched_by_double_click():
    """双击运行时（非命令行）出错后暂停，让用户能看清错误"""
    if os.environ.get('MB_NO_PAUSE'):
        return
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n按回车键退出…")
    except Exception:
        pass


def _parse_args(argv):
    """命令行参数：--port N / --no-browser / --help"""
    port, no_browser = None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--port") and i + 1 < len(argv):
            try:
                port = int(argv[i + 1]); i += 2; continue
            except ValueError:
                print(f"[错误] 端口必须是数字：{argv[i + 1]}", flush=True)
                return None, None
        elif a.startswith("--port="):
            try:
                port = int(a.split("=", 1)[1])
            except ValueError:
                print(f"[错误] 端口必须是数字：{a}", flush=True)
                return None, None
        elif a in ("--no-browser", "-n"):
            no_browser = True
        elif a in ("-h", "--help"):
            print(BANNER)
            print("  用法:  宝宝音乐盒.exe [选项]")
            print("    -p, --port N     指定端口（默认 8082，被占用则往上找）")
            print("    -n, --no-browser 不自动打开浏览器")
            print("    -h, --help       显示本帮助")
            print("\n  也可以用环境变量 MB_PORT 指定端口。")
            return "help", None
        i += 1
    return port, no_browser


def main():
    print(BANNER)
    arg_port, no_browser = _parse_args(sys.argv[1:])
    if arg_port == "help":
        return 0

    # 已经有实例在跑？直接把浏览器打开到它，不再起第二个 —— 双击第二次的用户
    # 本来就会看到两个黑窗口、两个页面，很困惑。用户显式指定了端口就跳过这一步。
    if not arg_port and not os.environ.get('MB_PORT'):
        rp, rh = _find_running_instance()
        if rp:
            print(f"[提示] 宝宝音乐盒已经在运行了（端口 {rp}），直接打开它。", flush=True)
            print(f"       它的数据目录：{(rh or {}).get('data_dir')}", flush=True)
            print(f"       想重新启动，请先关掉那个窗口，再双击本程序。", flush=True)
            if not no_browser:
                try:
                    webbrowser.open(f"http://localhost:{rp}/player.html")
                except Exception:
                    pass
            _pause_if_launched_by_double_click()
            return 0

    try:
        import server
    except Exception:
        print("[错误] 无法加载服务模块 server.py：")
        traceback.print_exc()
        _pause_if_launched_by_double_click()
        return 1

    # 端口优先级：命令行 --port > 环境变量 MB_PORT > 自动挑（8082 起）
    port = arg_port or int(os.environ.get('MB_PORT', 0)) or _pick_port(8082)
    if port != 8082:
        print(f"[信息] 使用端口 {port}")
    server.PORT = port
    os.environ['MB_PORT'] = str(port)

    print(f"  访问地址: http://localhost:{port}/player.html")
    print(f"  数据目录: {server.DATA_DIR}")
    if not (server.DATA_DIR / 'photos').exists():
        print("  [提示] 还没有照片：把图片放进上面的 photos 文件夹，刷新页面即可看到轮播")
    print("  停止服务: 关闭本窗口（或按 Ctrl+C）")
    print("=" * 46, flush=True)

    if not no_browser:
        threading.Thread(target=_wait_and_open, args=(port,), daemon=True).start()

    try:
        server.serve()
    except KeyboardInterrupt:
        pass
    except Exception:
        print("\n[错误] 服务异常退出：")
        traceback.print_exc()
        _pause_if_launched_by_double_click()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
