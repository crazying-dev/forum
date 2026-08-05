"""从 CDN favicon 生成 PWA 图标（一次性工具，可重复运行）。

输出到 main/static/pwa/：
- icon-192.png / icon-512.png：常规图标，保留透明背景
- maskable-512.png：主题色背景 + 内容缩至安全区（66%）
- apple-touch-icon.png：180x180，主题色背景（iOS 透明背景会渲染成黑色）
"""

import io
import sys
from pathlib import Path

import requests
from PIL import Image

FAVICON_URL = "https://img.crazying-dev.top/text/one/favicon.png"
OUT_DIR = Path(__file__).resolve().parent.parent / "main" / "static" / "pwa"
THEME_COLOR = (106, 140, 137)  # #6A8C89，与 base.html theme-color 一致


def _paste_centered(canvas: Image.Image, icon: Image.Image, ratio: float) -> None:
	"""把 icon 缩放后居中贴到画布上，保证 maskable 安全区（66%）不越界。"""
	size = int(canvas.width * ratio)
	content = icon.resize((size, size), Image.LANCZOS)
	pos = ((canvas.width - size) // 2, (canvas.height - size) // 2)
	canvas.alpha_composite(content, pos)


def main() -> int:
	resp = requests.get(FAVICON_URL, timeout=15)
	resp.raise_for_status()
	img = Image.open(io.BytesIO(resp.content))
	print(f"favicon: size={img.size} mode={img.mode}")
	if img.mode != "RGBA":
		img = img.convert("RGBA")
	# 原图小于目标尺寸时先放大到 512，避免小图直接拉糊
	if max(img.size) < 512:
		img = img.resize((512, 512), Image.LANCZOS)

	OUT_DIR.mkdir(parents=True, exist_ok=True)

	img.resize((192, 192), Image.LANCZOS).save(OUT_DIR / "icon-192.png")
	img.resize((512, 512), Image.LANCZOS).save(OUT_DIR / "icon-512.png")

	maskable = Image.new("RGBA", (512, 512), THEME_COLOR + (255,))
	_paste_centered(maskable, img, 0.66)
	maskable.save(OUT_DIR / "maskable-512.png")

	apple = Image.new("RGBA", (180, 180), THEME_COLOR + (255,))
	_paste_centered(apple, img, 0.8)
	apple.save(OUT_DIR / "apple-touch-icon.png")

	print(f"done -> {OUT_DIR}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
