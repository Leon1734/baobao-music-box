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


def _pick_port(start=8082, tries=8):
    """端口被占就往上找，最多试 tries 个"""
    for p in range(start, start + tries * 10, 10):
        if _port_free(p):
            return p
    return start


def _wait_and_open(port, timeout=30):
    """等服务真的起来了再开浏览器，避免打开一个「无法访问」的页面"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not _port_free(port):          # 端口被占用 = 服务已监听
            time.sleep(0.4)
            try:
                webbrowser.open(f"http://localhost:{port}/player.html")
            except Exception:
                pass
            return
        time.sleep(0.3)
    print(f"[警告] 等待服务超时，请手动打开 http://localhost:{port}/player.html", flush=True)


def _pause_if_launched_by_double_click():
    """双击运行时（非命令行）出错后暂停，让用户能看清错误"""
    if os.environ.get('MB_NO_PAUSE'):
        return
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n按回车键退出…")
    except Exception:
        pass


def main():
    print(BANNER)
    try:
        import server
    except Exception:
        print("[错误] 无法加载服务模块 server.py：")
        traceback.print_exc()
        _pause_if_launched_by_double_click()
        return 1

    port = int(os.environ.get('MB_PORT', 0)) or _pick_port(8082)
    if port != 8082:
        print(f"[信息] 8082 被占用，改用端口 {port}")
    server.PORT = port
    os.environ['MB_PORT'] = str(port)

    print(f"  访问地址: http://localhost:{port}/player.html")
    print(f"  数据目录: {server.DATA_DIR}")
    if not (server.DATA_DIR / 'photos').exists():
        print("  [提示] 还没有照片：把图片放进上面的 photos 文件夹，刷新页面即可看到轮播")
    print("  停止服务: 关闭本窗口（或按 Ctrl+C）")
    print("=" * 46, flush=True)

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
