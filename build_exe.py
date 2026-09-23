# -*- coding: utf-8 -*-
"""
打包 Windows 免安装单文件 exe

用法:
    python build_exe.py            # 用系统 Python（需带 pyinstaller）
    D:\\Programs\\Python313\\python.exe build_exe.py

产物:
    dist/宝宝音乐盒.exe          单文件，双击即用，无需装 Python
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
NAME = "宝宝音乐盒"

# 打进 exe 的只读资源
#   · 程序本体（player.html / 图标 / PWA）
#   · photos_web/  —— 照片的压缩版（轮播实际显示的就是它，4 张共 ~800KB），
#                     打进包用户开箱就有照片轮播；原图太大(80MB)不入包
#   · 音源/        —— 在线音源 .js，打进包开箱就能在线搜歌
#   · config.json  —— 音源密钥，打进包开箱就能在线播放
# 用户仍可在 exe 同级放同名文件覆盖（exe 同级优先）
BUNDLE = [
    "player.html",
    "manifest.json",
    "sw.js",
    "favicon.png",
    "icon-192.png",
    "icon-512.png",
    "kids_cache.json",
]
BUNDLE_DIRS = [
    "photos_web",
    "音源",
]
BUNDLE_OPT = [
    "config.json",          # 有就打进去（密钥）；没有也能打，只是在线播放要用户自己配
]


def main():
    missing = [f for f in BUNDLE if not (HERE / f).exists()]
    if missing:
        print(f"[错误] 缺少资源文件: {missing}")
        return 1

    for d in ("build", "dist"):
        p = HERE / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                  # 单文件
        "--console",                  # 保留控制台：用户能看到日志，关窗即停服务
        "--noconfirm",
        "--clean",
        "--name", NAME,
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE / "build"),
    ]
    if (HERE / "app.ico").exists():
        cmd += ["--icon", str(HERE / "app.ico")]
    for f in BUNDLE:
        # 用绝对路径：指定 --specpath 后，--add-data 的相对路径会以 spec 目录为基准解析
        cmd += ["--add-data", f"{HERE / f}{os.pathsep}."]
    for d in BUNDLE_DIRS:
        src = HERE / d
        if src.is_dir():
            n = len(list(src.glob("*")))
            print(f"  打包目录 {d}/  ({n} 个文件)")
            cmd += ["--add-data", f"{src}{os.pathsep}{d}"]
        else:
            print(f"  [跳过] 目录不存在: {d}/")
    for f in BUNDLE_OPT:
        src = HERE / f
        if src.exists():
            print(f"  打包配置 {f}  ✅（含密钥，开箱即用）")
            cmd += ["--add-data", f"{src}{os.pathsep}."]
        else:
            print(f"  [跳过] {f} 不存在 → 在线播放需用户自行配置")

    cmd.append(str(HERE / "app.py"))

    print("\n执行:", " ".join(cmd[:8]), "…")
    r = subprocess.run(cmd, cwd=str(HERE))
    if r.returncode != 0:
        print("[失败] PyInstaller 返回非零退出码")
        return r.returncode

    exe = HERE / "dist" / f"{NAME}.exe"
    if not exe.exists():
        print("[失败] 没有生成 exe")
        return 1

    size_mb = exe.stat().st_size / 1048576
    print(f"\n✅ 打包完成: {exe}")
    print(f"   体积: {size_mb:.1f} MB")
    print(f"\n分发方式：把这个 exe 单独发给别人即可（免安装、免 Python）。")
    print(f"照片、音源、密钥都已打进 exe —— 双击就有轮播和在线播放。")
    print(f"用户想加自己的照片/音源，在 exe 旁边建 photos/ 或 音源/ 即可（同级优先）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
