#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把桌面版的资源同步进 Android 工程（Android 版不复制代码，直接复用同一份文件）。

用法:  python tools/sync_android_assets.py

同步内容:
  server.py                  -> android/app/src/main/python/server.py   (Chaquopy 原样运行)
  player.html, manifest.json,
  sw.js, favicon.png,
  icon-*.png, kids_cache.json-> android/app/src/main/assets/
  photos_web/, 音源/          -> android/app/src/main/assets/
  icon-512.png               -> android/app/src/main/res/mipmap-*/ic_launcher.png

这样 Android 和 Windows 共用一份播放器代码：改完 player.html 跑一下本脚本即可。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AND = ROOT / "android" / "app" / "src" / "main"
ASSETS = AND / "assets"
PYDIR = AND / "python"
RES = AND / "res"

SINGLE_FILES = [
    "player.html", "manifest.json", "sw.js", "favicon.png",
    "icon-192.png", "icon-512.png", "kids_cache.json",
]
DIRS = ["photos_web", "音源"]
# 大图原片不进 APK（80MB+），安卓只用压缩版 photos_web/


def copy_file(src: Path, dst: Path) -> bool:
    if not src.is_file():
        print(f"  ⚠️  跳过（不存在）: {src.relative_to(ROOT)}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  ✅ {src.relative_to(ROOT)}  ->  {dst.relative_to(ROOT)}  ({src.stat().st_size:,} B)")
    return True


def copy_dir(src: Path, dst: Path) -> int:
    if not src.is_dir():
        print(f"  ⚠️  跳过（不存在）: {src.relative_to(ROOT)}")
        return 0
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    n = sum(len(fs) for _, _, fs in os.walk(dst))
    size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(f"  ✅ {src.relative_to(ROOT)}/  ->  {dst.relative_to(ROOT)}/  ({n} 个文件, {size:,} B)")
    return n


def main() -> int:
    if not (ROOT / "player.html").is_file():
        print(f"❌ 找不到 player.html，ROOT 判断错了？ROOT={ROOT}")
        return 1

    print("同步播放器代码 -> Android assets")
    for f in SINGLE_FILES:
        copy_file(ROOT / f, ASSETS / f)
    for d in DIRS:
        copy_dir(ROOT / d, ASSETS / d)

    print("\n同步服务端 -> Chaquopy python 目录")
    copy_file(ROOT / "server.py", PYDIR / "server.py")

    print("\n生成启动图标")
    icon = ROOT / "icon-512.png"
    if icon.is_file():
        # 各密度用同一张图（系统会自己缩放）；够用且省事
        for d in ["mipmap-mdpi", "mipmap-hdpi", "mipmap-xhdpi",
                  "mipmap-xxhdpi", "mipmap-xxxhdpi"]:
            copy_file(icon, RES / d / "ic_launcher.png")
    else:
        print("  ⚠️  没有 icon-512.png，图标会缺失（构建会失败）")

    # 统计 APK 里会带多少资源
    total = sum(f.stat().st_size for f in ASSETS.rglob("*") if f.is_file())
    print(f"\nassets 合计: {total/1024/1024:.2f} MB")
    print("完成。接下来:  git push  ->  GitHub Actions 自动构建 APK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
