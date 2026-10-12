"""Builds vfx/textures/glyph_atlas.png: a 16x16 grid of 64px "token" glyphs.

R = crisp glyph coverage, G = blurred halo (for cheap glow), B = cell-local
vertical gradient (used for scanline shimmer), A = 1.
Run: python3 vfx/tools/make_glyph_atlas.py
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CELL, GRID = 64, 16
LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
CJK = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

ascii_part = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz{}[]()<>/\\|#$%&*+=-_~^:;!?@"
math_part = "λΣΔΩπθφψ∇∂∫∑∏√∞≈≠≤≥∈∀∃⊕⊗→←↑↓⇒αβγδεμσ"
block_part = "░▒▓█▀▄▌▐■□▪▫◆◇○●◎"
kana_part = ("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
             "ガギグゲゴザジズゼゾダヂヅデドバビブベボ")
cjk_part = "文字言語智能模型数据向量注意力神经网络学习推理生成序列编码解码层"

glyphs = list(dict.fromkeys(ascii_part + math_part + block_part + kana_part + cjk_part))
glyphs = (glyphs * 2)[: GRID * GRID]

f_latin = ImageFont.truetype(LATIN, 50)
f_cjk = ImageFont.truetype(CJK, 52)

def font_for(ch):
    return f_cjk if ord(ch) > 0x3000 else f_latin

crisp = Image.new("L", (CELL * GRID, CELL * GRID), 0)
draw = ImageDraw.Draw(crisp)
for i, ch in enumerate(glyphs):
    cx, cy = (i % GRID) * CELL + CELL // 2, (i // GRID) * CELL + CELL // 2
    draw.text((cx, cy), ch, fill=255, font=font_for(ch), anchor="mm")

halo = crisp.filter(ImageFilter.GaussianBlur(5)).point(lambda v: min(255, int(v * 2.2)))
grad = Image.new("L", crisp.size)
grad.putdata([int(255 * ((y % CELL) / (CELL - 1))) for y in range(crisp.size[1]) for _ in range(crisp.size[0])])
alpha = Image.new("L", crisp.size, 255)

out = os.path.join(os.path.dirname(__file__), "..", "textures", "glyph_atlas.png")
Image.merge("RGBA", (crisp, halo, grad, alpha)).save(out)
print("wrote", os.path.abspath(out), len(set(glyphs)), "unique glyphs")
