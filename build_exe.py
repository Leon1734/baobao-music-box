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

# 打进 exe 的只读资源（用户数据 photos/音源/config.json 不放，放 exe 旁边）
BUNDLE = [
    "player.html",
    "manifest.json",
    "sw.js",
    "favicon.png",
    "icon-192.png",
    "icon-512.png",
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
    cmd.append(str(HERE / "app.py"))

    print("执行:", " ".join(cmd[:8]), "…")
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
    print(f"用户首次运行会在 exe 旁边自动使用 photos/ 音源/config.json（可自行创建）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
