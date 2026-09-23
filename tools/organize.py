"""一键整理 Music 目录：把散落在根目录的文件分类归档。

⭐ 铁律：server.py / app.py / build_exe.py 用 DATA_DIR=项目根 直接按文件名找东西，
   所以下面 KEEP_AT_ROOT 里的东西**一个都不能挪**，挪了应用就崩。
   判断依据是实测的引用关系（grep 出来的），不是猜的。
"""
import os, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# —— 必须留在根目录（被 server.py / player.html / build_exe.py 按名字引用）——
KEEP_AT_ROOT = {
    # 程序本体
    "app.py", "server.py", "player.html", "build_exe.py", "requirements.txt",
    # PWA：player.html 里以 /xxx 绝对路径引用
    "manifest.json", "sw.js", "favicon.png", "icon-192.png", "icon-512.png",
    # 配置（server.py 按名读 config.json）
    "config.json", "config.example.json",
    # 运行时缓存（server.py 写在 DATA_DIR）
    "kids_cache.json", "lyric_cache.json",
    # 用户双击的启动器
    "启动音乐盒.bat", "停止音乐盒.bat", "预览最新版.bat",
    # 说明文档
    "README.md", "IDEA.md", "DEVELOPMENT_PLAN.md",
}

# —— 资源目录：留在根（URL / 打包清单直接引用）——
KEEP_DIRS = {"音源", "wallpapers", "photos", "photos_web",
             "android", ".github", "dist", "release_pkg", "build", "tools",
             "docs", "reference", "logs"}

MOVES = [
    # 测试/预览脚本 → tools/
    ("verify.py", "tools"), ("verify_ui.py", "tools"), ("verify_fs.py", "tools"),
    ("preview.py", "tools"), ("stress.py", "tools"), ("gen_icons.py", "tools"),
    # 本地网页版遗留（已不发布浏览器版）
    ("server.js", "tools"), ("lx-loader.js", "tools"), ("test_lx.js", "tools"),
    ("_start.bat", "tools"), ("_cap.ps1", "tools"), ("_list.ps1", "tools"),
    # 日志 → logs/
    ("server.log", "logs"), ("server.log.prev2", "logs"),
    # 参考项目 → reference/
    ("lx-music-desktop", "reference"), ("AudioDock", "reference"), ("rustmusic-ref", "reference"),
]

# 临时垃圾直接删
JUNK_PREFIX = ("_screen", "_app", "_top", "_app_top", "_foot", "_probe", "_shot",
               "_fs", "_fs2", "_tabs", "_syntax_check", "_verify", "_player.bak",
               "_verify_out", "_verify_album", "_verify_8082", "_verify_kids")


def main():
    os.chdir(ROOT)
    made = []
    for d in ("tools", "docs", "docs/screenshots", "logs", "reference"):
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            os.makedirs(p); made.append(d)
    if made:
        print("新建目录:", ", ".join(made))

    # 1) 截图归档
    shots = os.path.join(ROOT, "docs", "screenshots")
    moved_shots = 0
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            continue
        if name.startswith("shot_") or name.startswith("预览-"):
            shutil.move(p, os.path.join(shots, name)); moved_shots += 1
    for sub in ("verify_shots", "preview"):
        s = os.path.join(ROOT, sub)
        if os.path.isdir(s):
            dst = os.path.join(shots, sub)
            if os.path.isdir(dst):
                for f in os.listdir(s):
                    shutil.move(os.path.join(s, f), os.path.join(dst, f))
                os.rmdir(s)
            else:
                shutil.move(s, dst)
    print(f"截图归档 → docs/screenshots/ : {moved_shots} 张散图 + verify_shots/ + preview/")

    # 2) 分类移动
    for name, dest in MOVES:
        src = os.path.join(ROOT, name)
        if not os.path.exists(src):
            continue
        dst = os.path.join(ROOT, dest, name)
        if os.path.exists(dst):
            print(f"  跳过（目标已存在）: {name}")
            continue
        shutil.move(src, dst)
    cnt = {}
    for name, dest in MOVES:
        if os.path.exists(os.path.join(ROOT, dest, name)):
            cnt[dest] = cnt.get(dest, 0) + 1
    for k, v in sorted(cnt.items()):
        print(f"归入 {k}/ : {v} 项")

    # 3) 清垃圾
    killed = []
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            continue
        base, ext = os.path.splitext(name)
        if any(base.startswith(t) or name.startswith(t) for t in JUNK_PREFIX):
            if name in KEEP_AT_ROOT:
                continue
            try:
                os.remove(p); killed.append(name)
            except Exception as e:
                print(f"  删不掉 {name}: {e}")
    print(f"清理临时文件: {len(killed)} 个")
    for k in killed:
        print("   -", k)

    # 4) 校验：一个都不能少的核心文件
    need = ["app.py", "server.py", "player.html", "build_exe.py", "manifest.json",
            "sw.js", "favicon.png", "icon-192.png", "icon-512.png", "config.json"]
    missing = [n for n in need if not os.path.exists(os.path.join(ROOT, n))]
    needdirs = ["音源", "wallpapers", "photos_web"]
    missdirs = [d for d in needdirs if not os.path.isdir(os.path.join(ROOT, d))]
    print("\n" + "=" * 52)
    if missing or missdirs:
        print("❌ 缺核心文件:", missing, "缺目录:", missdirs)
        return 1
    print("✅ 核心文件与资源目录齐全")
    over = [n for n in os.listdir(ROOT)
            if os.path.isfile(os.path.join(ROOT, n)) and n not in KEEP_AT_ROOT
            and not any(n.startswith(t) for t in JUNK_PREFIX)]
    if over:
        print("⚠️ 根目录仍有未归类文件:", over)
    return 0


if __name__ == "__main__":
    sys.exit(main())
