"""Render the generated walk from front/back and lay it out next to the reference GIF.

    python render_compare.py <in_char.fbx> <reference.gif> <out_dir> [--azim DEG] [--frames 0,2,4]

Writes <out_dir>/cmp_XX.png per anim frame plus <out_dir>/compare.gif.
Reference GIF frame for anim frame t is REF_OFFSET + t/2 (the GIF is ~15 fps).
"""
import math
import os
import sys

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import walk_gen  # noqa: E402

REF_OFFSET = 16  # GIF frame showing right-foot contact


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_render(res=(320, 560)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = res
    w = bpy.data.worlds.new("w")
    w.color = (0.55, 0.62, 0.78)
    sc.world = w
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    cam = bpy.data.cameras.new("cam")
    cam.lens = 85
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def main():
    argv = sys.argv[1:]
    fbx, gif, out = argv[0], argv[1], argv[2]
    azim = float(argv[argv.index("--azim") + 1]) if "--azim" in argv else 0.0
    frames = list(range(0, walk_gen.CYCLE, 2))
    if "--frames" in argv:
        frames = [int(x) for x in argv[argv.index("--frames") + 1].split(",")]
    os.makedirs(out, exist_ok=True)
    walk_gen.build(fbx)
    co = setup_render()
    sc = bpy.context.scene
    ref = Image.open(gif)
    dist, height, aim = 3.6, 1.15, (0, 0, 0.64)
    tiles = []
    for t in frames:
        sc.frame_set(t)
        imgs = []
        for view, base in (("front", -90.0), ("back", 90.0)):
            a = math.radians(base + azim)  # same yaw for both: emulates a turned subject
            co.location = (dist * math.cos(a), dist * math.sin(a), height)
            look_at(co, aim)
            sc.render.filepath = os.path.join(out, f"_{view}.png")
            bpy.ops.render.render(write_still=True)
            imgs.append(Image.open(sc.render.filepath).convert("RGB"))
        g = REF_OFFSET + t // 2
        ref.seek(g)
        r = ref.convert("RGB")
        rf = r.crop((40, 40, 340, 624)).resize((288, 560))
        rb = r.crop((560, 40, 860, 624)).resize((288, 560))
        tile = Image.new("RGB", (288 * 2 + 320 * 2, 560), "white")
        tile.paste(rf, (0, 0))
        tile.paste(imgs[0], (288, 0))
        tile.paste(imgs[1], (288 + 320, 0))
        tile.paste(rb, (288 + 640, 0))
        ImageDraw.Draw(tile).text((6, 6), f"anim {t} / ref {g}", fill="black")
        tile.save(os.path.join(out, f"cmp_{t:02d}.png"))
        tiles.append(tile)
    tiles[0].save(os.path.join(out, "compare.gif"), save_all=True, append_images=tiles[1:],
                  duration=66, loop=0)


if __name__ == "__main__":
    main()
