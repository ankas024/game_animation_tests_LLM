"""Finish VIGIL: grade + grain + letterbox the rendered frames, add the title card and score.

    python finish.py --frames renders/frames --audio renders/vigil.wav --out vigil.mp4

Needs ffmpeg, numpy and Pillow. Title fonts (OFL) are fetched from the
google/fonts repository on first use; DejaVu Serif is the fallback.
"""

import argparse
import os
import subprocess
import tempfile
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FPS = 24
PICTURE_END = 840
TITLE_FRAMES = 96
OUT_W, OUT_H = 1920, 1080
SCOPE_H = 804                       # 2.39:1 picture inside a 16:9 frame
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "renders", "fonts")
FONTS = {
    "title": ("Cinzel[wght].ttf", "cinzel/Cinzel%5Bwght%5D.ttf"),
    "tag": ("CormorantGaramond-Italic[wght].ttf", "cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf"),
}


def font(kind, size):
    name, url = FONTS[kind]
    path = os.path.join(FONT_DIR, name)
    if not os.path.exists(path):
        try:
            os.makedirs(FONT_DIR, exist_ok=True)
            urllib.request.urlretrieve("https://raw.githubusercontent.com/google/fonts/main/ofl/" + url, path)
        except OSError:
            return ImageFont.truetype("DejaVuSerif.ttf", size)
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([500 if kind == "title" else 400])
    except (OSError, AttributeError):
        pass
    return f


def tracked_text(draw, center, text, fnt, tracking, fill):
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = center[0] - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, center[1]), ch, font=fnt, fill=fill, anchor="lm")
        x += w + tracking


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def title_frames(outdir):
    """96 frames on black: title blooms in on the bell, tagline follows, both fade out."""
    big, small = font("title", 132), font("tag", 44)
    layer = Image.new("L", (OUT_W, OUT_H), 0)
    d = ImageDraw.Draw(layer)
    cy = OUT_H // 2 - 26
    tracked_text(d, (OUT_W / 2, cy), "VIGIL", big, 52, 255)
    tag = Image.new("L", (OUT_W, OUT_H), 0)
    d2 = ImageDraw.Draw(tag)
    tracked_text(d2, (OUT_W / 2, cy + 112), "the last light", small, 6, 255)
    d2.line([(OUT_W / 2 - 150, cy + 76), (OUT_W / 2 + 150, cy + 76)], fill=150, width=1)
    glow = layer.filter(ImageFilter.GaussianBlur(18))
    halo = layer.filter(ImageFilter.GaussianBlur(60))
    L = np.asarray(layer, np.float32) / 255
    G = np.asarray(glow, np.float32) / 255
    Hh = np.asarray(halo, np.float32) / 255
    Tg = np.asarray(tag, np.float32) / 255
    col = np.array([212, 222, 238], np.float32)
    glow_col = np.array([120, 160, 230], np.float32)
    os.makedirs(outdir, exist_ok=True)
    for i in range(TITLE_FRAMES):
        f = PICTURE_END + 1 + i
        a = smooth((f - 860) / 20) * (1 - smooth((f - 914) / 20))
        b = smooth((f - 874) / 18) * (1 - smooth((f - 910) / 20))
        rise = 1.0 + 0.4 * (1 - smooth((f - 860) / 30))  # glow settles as the bell rings out
        img = (L[..., None] * col * a + G[..., None] * glow_col * 0.55 * a * rise
               + Hh[..., None] * glow_col * 0.35 * a + Tg[..., None] * col * 0.8 * b)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(os.path.join(outdir, f"t_{i:04d}.png"))


def run(cmd):
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default=os.path.join(HERE, "renders", "frames"))
    ap.add_argument("--audio", default=os.path.join(HERE, "renders", "vigil.wav"))
    ap.add_argument("--out", default=os.path.join(HERE, "vigil.mp4"))
    ap.add_argument("--crf", default="17")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        title_frames(os.path.join(tmp, "title"))
        pad_y = (OUT_H - SCOPE_H) // 2
        fade_out_start = (PICTURE_END - 30) / FPS
        grade = ",".join([
            f"scale={OUT_W}:{SCOPE_H}:flags=lanczos",
            "colorbalance=rs=-0.02:gs=0.0:bs=0.035:rh=0.025:gh=0.008:bh=-0.02",
            "eq=contrast=1.04:saturation=0.96",
            "vignette=angle=PI/4.6",
            "noise=alls=7:allf=t+u",
            "fade=t=in:st=0:d=0.75",
            f"fade=t=out:st={fade_out_start:.3f}:d={30 / FPS:.3f}",
            f"pad={OUT_W}:{OUT_H}:0:{pad_y}:black",
            "setsar=1",
        ])
        filt = (f"[0:v]{grade}[pic];[1:v]format=rgb24,setsar=1[ttl];"
                f"[pic][ttl]concat=n=2:v=1:a=0,format=yuv420p[v]")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-framerate", str(FPS), "-i", os.path.join(a.frames, "vigil_%04d.png"),
             "-framerate", str(FPS), "-i", os.path.join(tmp, "title", "t_%04d.png"),
             "-i", a.audio,
             "-filter_complex", filt, "-map", "[v]", "-map", "2:a",
             "-c:v", "libx264", "-preset", "slow", "-crf", a.crf, "-tune", "film",
             "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", a.out])
    print("wrote", a.out)


if __name__ == "__main__":
    main()
