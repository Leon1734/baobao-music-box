"""生成宝宝音乐盒 PWA 图标"""
from PIL import Image, ImageDraw
import math, os

OUT = os.path.dirname(os.path.abspath(__file__))

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    # 圆角方形背景（渐变）
    r = int(size*0.22)
    bg = Image.new("RGBA", (size, size), (0,0,0,0))
    bd = ImageDraw.Draw(bg)
    # 手动渐变
    for y in range(size):
        t = y/size
        cr = int(0x1A + (0x0F-0x1A)*t)
        cg = int(0x1A + (0x34-0x1A)*t)
        cb = int(0x2E + (0x60-0x2E)*t)
        bd.line([(0,y),(size,y)], fill=(cr,cg,cb,255))
    mask = Image.new("L", (size,size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0,0,size-1,size-1], radius=r, fill=255)
    img.paste(bg, (0,0), mask)

    d = ImageDraw.Draw(img)
    s = size/512.0
    # 音符主体（粉色）
    PINK=(0xFF,0x6B,0x9D,255); PINK2=(0xFF,0x8F,0xB4,255)
    TEAL=(0x4E,0xCD,0xC4,255); YEL=(0xFF,0xE6,0x6D,255)
    # 符头（两个椭圆）
    hw, hh = int(78*s), int(58*s)
    d.ellipse([int(140*s), int(330*s), int(140*s)+hw*2, int(330*s)+hh*2], fill=PINK)
    d.ellipse([int(280*s), int(290*s), int(280*s)+hw*2, int(290*s)+hh*2], fill=PINK2)
    # 符杆
    d.rectangle([int(140*s)+hw*2-int(16*s), int(120*s), int(140*s)+hw*2, int(330*s)+hh], fill=PINK)
    d.rectangle([int(280*s)+hw*2-int(16*s), int(80*s), int(280*s)+hw*2, int(290*s)+hh], fill=PINK2)
    # 符梁
    d.polygon([(int(140*s)+hw*2-int(16*s), int(120*s)),
               (int(280*s)+hw*2, int(80*s)),
               (int(280*s)+hw*2, int(80*s)+int(52*s)),
               (int(140*s)+hw*2-int(16*s), int(120*s)+int(52*s))], fill=YEL)
    # 声波条（右下，青色）
    for i,(bx,bh) in enumerate([(360,70),(400,120),(440,90)]):
        d.rounded_rectangle([int(bx*s), int((430-bh)*s), int(bx*s)+int(22*s), int(430*s)],
                            radius=int(11*s), fill=TEAL)
    return img

for sz in (192, 512):
    p = os.path.join(OUT, f"icon-{sz}.png")
    make_icon(sz).save(p, "PNG")
    print(f"生成 {p}")

# favicon 32
make_icon(32).save(os.path.join(OUT, "favicon.png"), "PNG")
print("生成 favicon.png")
print("✅ 图标生成完成")
