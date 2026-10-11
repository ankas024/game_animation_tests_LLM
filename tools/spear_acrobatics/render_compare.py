"""Render the animation with Workbench solid/textured shading next to the reference.

    python -I tools/spear_acrobatics/render_compare.py OUT_DIR [--frames -6-163:2] [--res 640x360]
        [--views A,B] [--mp4]

Frames are view-A frame numbers. Each output tile cmp_XXX.png has one row per
view: reference | ch_02 render, with the render's camera matching that view
(see clips.VIEWS). --mp4 writes OUT_DIR/compare.mp4 at 30 fps.
"""
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import clips  # noqa: E402
import rig  # noqa: E402
import scene  # noqa: E402

REF_DIR = os.path.join(scene.ROOT, "references/spear_acrobatics")


def parse_frames(spec):
    out = []
    for part in spec.split(","):
        step = 1
        if ":" in part:
            part, step = part.split(":")
            step = int(step)
        neg = part.startswith("-")
        a, _, b = part[1:].partition("-") if neg else part.partition("-")
        a = -int(a) if neg else int(a)
        out += list(range(a, int(b) + 1, step)) if b else [a]
    return [f for f in out if clips.F0 <= f <= clips.F1]


def gauss(vals, sigma):
    r = int(math.ceil(sigma * 3))
    w = [math.exp(-0.5 * (i / sigma) ** 2) for i in range(-r, r + 1)]
    n = len(vals)
    res = []
    for i in range(n):
        acc = ws = 0.0
        for k, wk in enumerate(w):
            j = min(max(i + k - r, 0), n - 1)
            acc += vals[j] * wk
            ws += wk
        res.append(acc / ws)
    return res


def view_dir(cam):
    a, e = math.radians(cam["az"]), math.radians(cam["el"])
    return Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), -math.sin(e)))


def camera_positions(tl, cam):
    frames, data = tl.bake()
    if "pos" in cam:
        return {f: Vector(cam["pos"]) for f in frames}
    xs, ys = gauss(data["hx"], cam["follow"]), gauss(data["hy"], cam["follow"])
    d = view_dir(cam)
    return {f: Vector((x, y, cam["aim_z"])) - d * cam["dist"] for f, x, y in zip(frames, xs, ys)}


def make_camera(sc, name, cam):
    co = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    sc.collection.objects.link(co)
    co.data.lens = cam["lens"]
    co.data.clip_end = 200
    co.rotation_euler = Euler((math.radians(90 - cam["el"]), 0, math.radians(-cam["az"])))
    return co


def main():
    argv = sys.argv[1:]
    out = argv[0]
    spec = argv[argv.index("--frames") + 1] if "--frames" in argv else f"{clips.F0}-{clips.F1}"
    res = argv[argv.index("--res") + 1] if "--res" in argv else "640x360"
    views = (argv[argv.index("--views") + 1] if "--views" in argv else "A,B").split(",")
    W, H = (int(v) for v in res.split("x"))
    frames = parse_frames(spec)
    os.makedirs(out, exist_ok=True)

    arm = scene.setup()
    sc = scene.setup_workbench((W, H))
    r = rig.Rig(arm)
    tl = clips.build_timeline()
    cams = {}
    for v in views:
        cam = clips.VIEWS[v]["cam"]
        cams[v] = (make_camera(sc, "Cam" + v, cam), camera_positions(tl, cam))
    for f in frames:
        r.apply(tl.at(f))
        tile = Image.new("RGB", (W * 2, H * len(views)), (20, 20, 24))
        for row, v in enumerate(views):
            co, pos = cams[v]
            co.location = pos[f]
            sc.camera = co
            bpy.context.view_layer.update()
            sc.render.filepath = os.path.join(out, "_render.png")
            bpy.ops.render.render(write_still=True)
            img = Image.open(sc.render.filepath).convert("RGB")
            g = clips.VIEWS[v]["ref"](f)
            if g is not None:
                ref = Image.open(os.path.join(REF_DIR, f"spear_acrobatics_{g:03d}.jpg")).convert("RGB")
                tile.paste(ref.resize((W, H)), (0, row * H))
            tile.paste(img, (W, row * H))
            d = ImageDraw.Draw(tile)
            d.text((8, row * H + 6), f"reference {g:03d}" if g is not None else "reference -",
                   fill=(20, 20, 30) if g is not None else (200, 200, 200))
            d.text((W + 8, row * H + 6), f"ch_02  view {v}  frame {f - clips.F0:03d}", fill=(20, 20, 30))
        tile.save(os.path.join(out, f"cmp_{f - clips.F0:03d}.png"))
    if "--mp4" in argv:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(clips.FPS),
                        "-pattern_type", "glob", "-i", os.path.join(out, "cmp_*.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
                        os.path.join(out, "compare.mp4")], check=True)


if __name__ == "__main__":
    main()
