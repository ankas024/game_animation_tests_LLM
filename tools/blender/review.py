"""
Contact-sheet review renders (Workbench).

usage: python -I review.py <out_dir> <cams comma list> <frames: a,b,c | a-b:step> [tag]
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import scene_util as su  # noqa: E402
import rigkit  # noqa: E402
import sword  # noqa: E402
import combo  # noqa: E402

CAMS = {
    "q34": ((-1.75, -1.85, 1.0), (0.0, 0.0, 0.68), 40),
    "side": ((-2.6, 0.0, 0.85), (0.0, 0.0, 0.7), 40),
    "front": ((0.25, -2.6, 0.95), (0.0, 0.0, 0.68), 40),
    "back": ((1.6, 3.2, 1.3), (0.0, -0.3, 0.65), 45),
    "top": ((-0.05, -0.35, 3.6), (0.0, -0.3, 0.0), 40),
    "left": ((3.6, -0.35, 0.85), (0.0, -0.35, 0.75), 45),
}


def parse_frames(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, rest = part.split("-")
            b, step = (rest.split(":") + ["1"])[:2]
            out += list(range(int(a), int(b) + 1, int(step)))
        else:
            out.append(int(part))
    return out


def main():
    out, cams, frames = sys.argv[-4], sys.argv[-3], sys.argv[-2]
    tag = sys.argv[-1]
    os.makedirs(out, exist_ok=True)
    arm, meshes = su.load_character()
    rig = rigkit.Rig(arm)
    rig.ensure_weapon_bone()
    sword.build_skinned(arm, rig)
    su.setup_workbench((300, 340))
    su.ground_grid()
    for m in meshes:
        m.color = (0.80, 0.64, 0.56, 1)
    T = combo.build()
    cam_objs = {n: su.add_camera(n, *CAMS[n]) for n in cams.split(",")}
    paths = []
    for f in parse_frames(frames):
        pose = T.sample(f)
        c, Wr, Wp = rig.apply(pose)
        hp = Wp[rigkit.P + "Hips"]
        for n, cam in cam_objs.items():
            loc, tgt, lens = CAMS[n]
            off = Vector((hp.x, hp.y, 0.0))
            cam.location = Vector(loc) + off
            d = Vector(tgt) + off - cam.location
            cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        bpy.context.view_layer.update()
        for n, cam in cam_objs.items():
            p = os.path.join(out, f"{tag}_{n}_{f:04d}.png")
            su.render_still(p, cam)
            subprocess.run(["convert", p, "-fill", "white", "-pointsize", "14",
                            "-annotate", "+6+16", f"{f} {n}", p], check=True)
            paths.append(p)
    cols = len(cam_objs) * (2 if len(cam_objs) <= 2 else 1)
    cols = max(cols, 4) if len(cam_objs) == 1 else cols
    subprocess.run(["montage"] + paths + ["-tile", f"{cols}x", "-geometry", "+1+1",
                                          "-background", "#111", os.path.join(out, f"{tag}_sheet.png")],
                   check=True)
    for p in paths:
        os.remove(p)


main()
