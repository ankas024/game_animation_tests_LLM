"""Build (and optionally render) the VIGIL cutscene.

Run with the Blender Python module (``pip install bpy==5.2.2``)::

    python cinematics/vigil/build.py --save-blend /tmp/vigil.blend
    python cinematics/vigil/build.py --render --frames 1-840 --out renders/frames

or inside Blender 5.2::

    blender -b -P cinematics/vigil/build.py -- --render --frames 481-620
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import character  # noqa: E402
import environment  # noqa: E402
import performance  # noqa: E402
import shots  # noqa: E402

CHAR_FBX = os.path.join(REPO, "assets/skeletal_meshes/characters/ch_02.fbx")
TEX_BODY = os.path.join(REPO, "assets/textures/SK_c002_tripo_rgb_69d181a3-f4af-4255-8e04-1ec596474e7e.jpg")
TEX_FACE = os.path.join(REPO, "assets/textures/SK_c002_face_text_fix.png")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--frames", default="1-%d" % shots.FRAME_END,
                    help="range 'a-b' or comma list '1,50,100'")
    ap.add_argument("--res", default="1920x804")
    ap.add_argument("--samples", type=int, default=14)
    ap.add_argument("--no-motion-blur", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "renders", "frames"))
    ap.add_argument("--save-blend", default=None)
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--export-fbx", default=None,
                    help="write the character with the baked performance (armature + skin) to FBX")
    return ap.parse_args(argv)


def build(args):
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    char_col = bpy.data.collections.new("CHARACTER")
    sc.collection.children.link(char_col)
    arm = character.import_character(CHAR_FBX, TEX_BODY, TEX_FACE, char_col)
    arm.location = (0.0, performance.Performance.START_Y, 0.0)
    rig = character.Rig(arm)
    perf = performance.Performance(rig, arm, frame_end=shots.FRAME_END)

    # The broken vault sits up-ahead of where she stops; the grace beam pours through it.
    stop_y = perf.stop_world_y
    hole = Vector((1.2, stop_y + 12.0, 22.4))
    beam_dir = (hole - Vector((0.0, stop_y, 0.0))).normalized()
    perf.bake(hole)
    print(f"[vigil] performance baked: stop at y={stop_y:.2f}  ({time.time() - t0:.1f}s)")

    env = environment.Cathedral(dict(stop_y=stop_y, hole=hole, beam_dir=beam_dir)).build()
    print(f"[vigil] set built ({time.time() - t0:.1f}s)")
    shots.Cinematography(perf, env, arm).build()
    rx, ry = (int(v) for v in args.res.split("x"))
    shots.render_settings(rx, ry, args.samples, motion_blur=not args.no_motion_blur)
    shots.compositor()

    # footstep contacts for the soundtrack
    os.makedirs(os.path.join(HERE, "renders"), exist_ok=True)
    with open(os.path.join(HERE, "renders", "contacts.json"), "w") as fh:
        json.dump([dict(frame=c[0], foot=c[1], x=c[2].x, y=c[2].y, scale=c[3]) for c in perf.contacts],
                  fh, indent=1)
    print(f"[vigil] scene ready ({time.time() - t0:.1f}s)")
    return perf


def export_fbx(path):
    """Character + baked 840-frame performance, Mixamo bone names intact, for game engines."""
    bpy.ops.object.select_all(action="DESELECT")
    arm = bpy.data.objects["CHAR_rig"]
    for o in [arm] + list(arm.children):
        if o.type in ("ARMATURE", "MESH"):
            o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=os.path.abspath(path), use_selection=True,
                             object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=False,
                             bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0.0,
                             path_mode="STRIP", axis_forward="-Z", axis_up="Y")


def frame_list(spec):
    if "-" in spec and "," not in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def render(args):
    sc = bpy.context.scene
    os.makedirs(args.out, exist_ok=True)
    for f in frame_list(args.frames):
        path = os.path.join(args.out, f"vigil_{f:04d}.png")
        if args.skip_existing and os.path.exists(path):
            continue
        t = time.time()
        sc.frame_set(f)
        live = [m for m in sc.timeline_markers if m.frame <= f and m.camera]
        if live:
            sc.camera = max(live, key=lambda m: m.frame).camera
        if not args.no_motion_blur:
            sc.render.use_motion_blur = shots.shot_at(f) in shots.MOTION_BLUR_SHOTS
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"[vigil] frame {f} -> {path} ({time.time() - t:.1f}s)", flush=True)


if __name__ == "__main__":
    a = parse_args()
    build(a)
    if a.export_fbx:
        export_fbx(a.export_fbx)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save_blend))
    if a.render:
        render(a)
