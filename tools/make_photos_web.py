#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 photos/ 原图压缩为 photos_web/ 网页尺寸版本（供轮播/头像秒开）。

用法:
    python tools/make_photos_web.py              # 增量压缩（推荐，可反复运行）
    python tools/make_photos_web.py --force      # 全部重压
    python tools/make_photos_web.py --max 1920 --quality 85

说明:
- 输出文件名与原图一致，但统一转成 JPEG；长边不超过 --max 像素；自动做 EXIF 旋转校正。
- 输出已存在且不旧于原图时会跳过（幂等）。
- server.py 的 /api/photos 会优先返回 photos_web/ 下的版本，网页端无需任何改动。
"""
import argparse
import sys
import time
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("缺少 Pillow，请先安装:  python -m pip install pillow  （或 uv pip install pillow）")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "photos"
DST = ROOT / "photos_web"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def human(n: int) -> str:
    return f"{n / 1024 / 1024:.2f}MB" if n >= 1024 * 1024 else f"{n / 1024:.0f}KB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1600, help="长边最大像素，默认 1600")
    ap.add_argument("--quality", type=int, default=82, help="JPEG 质量，默认 82")
    ap.add_argument("--force", action="store_true", help="忽略已有输出，全部重压")
    args = ap.parse_args()

    if not SRC.exists():
        sys.exit(f"找不到目录: {SRC}")
    DST.mkdir(exist_ok=True)

    files = sorted(f for f in SRC.iterdir() if f.suffix.lower() in EXTS)
    if not files:
        sys.exit("photos/ 里没有图片")

    done = skipped = 0
    total_in = total_out = 0
    for src in files:
        out = DST / (src.stem + ".jpg")
        if not args.force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            skipped += 1
            continue
        t0 = time.time()
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)          # 处理手机照片的旋转信息
            im.thumbnail((args.max, args.max), Image.LANCZOS)
            if im.mode in ("RGBA", "P", "LA"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            im.save(out, "JPEG", quality=args.quality, optimize=True, progressive=True)
        a, b = src.stat().st_size, out.stat().st_size
        total_in += a
        total_out += b
        done += 1
        print(f"[OK] {src.name}  {im.size[0]}x{im.size[1]}  {human(a)} -> {human(b)}  ({time.time() - t0:.1f}s)")

    print(f"\n完成：新压 {done} 张，跳过 {skipped} 张；本次合计 {human(total_in)} -> {human(total_out)}")
    print(f"输出目录: {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
