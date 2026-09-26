#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成妖精论坛 OG 分享图（1200×630）并写入 public/og-image.png。

设计：深色底（#161b22，与 manifest theme_color 一致）+ 品牌色光晕 + 圆形 logo
+ 站名「妖精论坛」+ 标语 + 域名。作为全站默认分享图（Open Graph / Twitter Card）。

依赖：Pillow + 系统中文字体（Noto Sans CJK）。
用法：python3 scripts/generate-og-image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 630
BG = (22, 27, 34)       # #161b22
BRAND = (87, 148, 145)  # #579491
TEXT = (232, 238, 237)  # #E8EEED
MUTED = (150, 169, 167) # #96A9A7

ROOT = Path(__file__).resolve().parents[1]
FAVICON = ROOT / "public" / "assets" / "img" / "favicon.png"
OUT = ROOT / "public" / "og-image.png"

FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]
FONT_REG_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(candidates, size):
    """加载字体：优先简体中文（SC）face，兼容 .ttc 多 face 字体。"""
    for path in candidates:
        if not Path(path).exists():
            continue
        fallback = None
        for idx in range(12):
            try:
                f = ImageFont.truetype(path, size, index=idx)
            except Exception:
                break
            family = f.getname()[0]
            if fallback is None:
                fallback = f
            if "SC" in family and "Mono" not in family:
                return f
        if fallback is not None:
            return fallback
    raise SystemExit("未找到可用中文字体（Noto Sans CJK），请先安装后重试")


def circle_logo(size):
    """圆形 logo（方形源图加圆形遮罩）。"""
    img = Image.open(FAVICON).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    canvas = Image.new("RGBA", (W, H), BG + (255,))

    # 品牌色光晕（两团低透明度圆 + 高斯模糊，制造氛围感）
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-160, -200, 460, 420), fill=BRAND + (36,))
    g.ellipse((820, 300, 1420, 900), fill=BRAND + (28,))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    canvas = Image.alpha_composite(canvas, glow)

    draw = ImageDraw.Draw(canvas)

    # 圆形 logo（顶部居中）
    logo_size = 132
    canvas.alpha_composite(circle_logo(logo_size), ((W - logo_size) // 2, 96))

    # 站名
    title_font = load_font(FONT_BOLD_CANDIDATES, 104)
    title = "妖精论坛"
    draw.text(((W - draw.textlength(title, font=title_font)) / 2, 264), title, font=title_font, fill=TEXT)

    # 品牌色短条
    bar_w, bar_h = 148, 8
    draw.rounded_rectangle(
        ((W - bar_w) / 2, 412, (W + bar_w) / 2, 412 + bar_h), radius=4, fill=BRAND
    )

    # 标语
    sub_font = load_font(FONT_REG_CANDIDATES, 38)
    sub = "罗小黑战记同人社区"
    draw.text(((W - draw.textlength(sub, font=sub_font)) / 2, 456), sub, font=sub_font, fill=MUTED)

    # 域名
    dom_font = load_font(FONT_REG_CANDIDATES, 26)
    dom = "yjlt.top"
    draw.text(((W - draw.textlength(dom, font=dom_font)) / 2, 552), dom, font=dom_font, fill=BRAND)

    canvas.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"已生成 {OUT}（{W}×{H}）")


if __name__ == "__main__":
    main()
