#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键发版：构建 exe → 同步 release_pkg → 提示上传。

用户要求：「每次升级完，生成相应版本的免安装 exe 版本，一次一次的升级迭代」
本脚本把这条流程固化，避免漏步骤。

用法:
    python tools/release_all.py              # 构建 + 同步本地发布包
    python tools/release_all.py --upload     # 再跑 tools/release.py 上传 GitHub Release
    python tools/release_all.py --no-node    # 不打 Node（exe 小 ~22MB，但免安装环境不能在线播放）

步骤:
    1. 读 tools/release.py 里的 TAG / ASSET_NAME（版本号的唯一真源）
    2. python build_exe.py                  → dist/宝宝音乐盒.exe
    3. 校验 dist 产物存在 + MD5
    4. 同步到 release_pkg/<TAG>-win64/（删旧同名目录）+ release_pkg/宝宝音乐盒.exe
    5. --upload 时调 tools/release.py 建 Release 并上传
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_EXE = ROOT / "dist" / "宝宝音乐盒.exe"
RELEASE_PY = ROOT / "tools" / "release.py"
RELEASE_PKG = ROOT / "release_pkg"


def read_release_meta():
    """从 tools/release.py 读 TAG 和 ASSET_NAME（单一真源）"""
    src = RELEASE_PY.read_text(encoding="utf-8")
    tag = re.search(r'^TAG\s*=\s*"([^"]+)"', src, re.M)
    name = re.search(r'^ASSET_NAME\s*=\s*"([^"]+)"', src, re.M)
    if not tag:
        print("[失败] tools/release.py 里找不到 TAG")
        sys.exit(1)
    return tag.group(1), (name.group(1) if name else f"baobao-music-box-{tag.group(1)}-win64.exe")


def md5(p: Path, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    upload = "--upload" in sys.argv
    tag, asset = read_release_meta()
    print("=" * 60)
    print(f"  一键发版 · {tag}")
    print("=" * 60)

    # ---- 1. 构建 exe ----
    print(f"\n[1/4] 构建 exe（build_exe.py）…")
    cmd = [sys.executable, str(ROOT / "build_exe.py")]
    if "--no-node" in sys.argv:
        cmd.append("--no-node")
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print("[失败] build_exe.py 返回非零"); sys.exit(1)
    if not DIST_EXE.exists():
        print(f"[失败] 没找到产物 {DIST_EXE}"); sys.exit(1)

    size_mb = DIST_EXE.stat().st_size / 1048576
    digest = md5(DIST_EXE)
    print(f"\n[2/4] 产物校验：{DIST_EXE.name}  {size_mb:.1f} MB  MD5 {digest[:16]}")

    # ---- 2. 同步 release_pkg ----
    print(f"\n[3/4] 同步本地发布包 release_pkg/")
    ver_dir = RELEASE_PKG / f"宝宝音乐盒-{tag}-win64"
    # 清掉旧的同 tag 目录（重建），并清掉其它版本的 *-win64 目录（防止用户点到旧版）
    if ver_dir.exists():
        shutil.rmtree(ver_dir)
    for old in RELEASE_PKG.glob("宝宝音乐盒-v*-win64"):
        if old.name != ver_dir.name:
            shutil.rmtree(old)
            print(f"  🗑  移除旧版本目录 {old.name}")
    ver_dir.mkdir(parents=True, exist_ok=True)
    dst1 = ver_dir / "宝宝音乐盒.exe"
    shutil.copy2(DIST_EXE, dst1)
    # release_pkg 根目录同时放一份（历史习惯）
    dst2 = RELEASE_PKG / "宝宝音乐盒.exe"
    shutil.copy2(DIST_EXE, dst2)
    if md5(dst1) != digest or md5(dst2) != digest:
        print("[失败] 复制后 MD5 不一致"); sys.exit(1)
    print(f"  ✅ {dst1.relative_to(ROOT)}  ({dst1.stat().st_size/1048576:.1f} MB)")
    print(f"  ✅ {dst2.relative_to(ROOT)}")

    # ---- 3. 上传（可选）----
    if upload:
        print(f"\n[4/4] 上传 GitHub Release（tools/release.py）…")
        r = subprocess.run([sys.executable, str(RELEASE_PY)], cwd=str(ROOT))
        if r.returncode != 0:
            print("[失败] release.py 返回非零"); sys.exit(1)
    else:
        print(f"\n[4/4] 跳过上传。要发 GitHub Release 加 --upload，或单跑：")
        print(f"      python tools/release.py")

    print(f"\n{'=' * 60}")
    print(f"  ✅ {tag} 免安装 exe 就绪")
    print(f"     dist/宝宝音乐盒.exe = release_pkg/宝宝音乐盒-{tag}-win64/宝宝音乐盒.exe")
    print(f"     MD5 {digest}")
    print("=" * 60)


if __name__ == "__main__":
    main()
