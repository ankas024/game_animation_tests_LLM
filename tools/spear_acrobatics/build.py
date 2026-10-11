"""Bake the spear acrobatics animation and export it.

    python -I tools/spear_acrobatics/build.py [--out DIR]

Writes <out>/A_ch02_SpearAcrobatics.fbx (ch_02 skeleton + spear bones, both
character meshes, the skinned spear and one baked 30 fps take; every bone
keyed on every frame, no curve simplification) and
<out>/A_ch02_SpearAcrobatics.json (frame mapping to both reference views,
root motion, spear-on-floor windows). Default out dir: assets/animations/combat.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import clips  # noqa: E402
import rig  # noqa: E402
import scene  # noqa: E402

KEY_LOC = {rig.P + "Hips"} | set(rig.SPEAR_FWD) | set(rig.SPEAR_BACK)


def bake(arm, r):
    tl = clips.build_timeline()
    sc = bpy.context.scene
    sc.render.fps = clips.FPS
    n = clips.F1 - clips.F0 + 1
    sc.frame_start, sc.frame_end = 0, n - 1
    sc.name = clips.NAME                     # FBX take name
    arm.animation_data_create()
    act = bpy.data.actions.new(clips.NAME)
    arm.animation_data.action = act
    info = dict(hips=[], spear_low=[], max_bone_offset=0.0)
    prev = {}
    for k in range(n):
        f = clips.F0 + k
        pose = tl.at(f)
        R, H = r.apply(pose)
        for pb in arm.pose.bones:
            q = pb.rotation_quaternion.copy()
            if pb.name in prev and q.dot(prev[pb.name]) < 0:   # keep quaternion keys continuous
                q.negate()
                pb.rotation_quaternion = q
            prev[pb.name] = q
            pb.keyframe_insert("rotation_quaternion", frame=k, group=pb.name)
            if pb.name in KEY_LOC:
                pb.keyframe_insert("location", frame=k, group=pb.name)
            else:
                info["max_bone_offset"] = max(info["max_bone_offset"], pb.location.length)
                pb.location = (0, 0, 0)
        h = H[rig.P + "Hips"]
        info["hips"].append((round(h.x, 4), round(h.y, 4), round(h.z, 4)))
        # lowest point of the shaft (planted / dragged on the floor when <= 0)
        centre, Fm, kk, nb = r.spear_state
        lo = min((centre + r.arc(Fm, kk, nb, s)[0]).z
                 for s in [rig.SPEAR_LEN * (i / 20 - 0.5) for i in range(21)])
        info["spear_low"].append(round(lo, 4))
    return act, info


def export(arm, path):
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for ob in arm.children:
        if ob.type == "MESH":
            ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0, armature_nodetype="NULL", path_mode="RELATIVE",
        mesh_smooth_type="FACE",
    )


def windows(mask):
    out, start = [], None
    for i, m in enumerate(mask + [False]):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append([start, i - 1])
            start = None
    return out


def write_meta(path, info):
    hips = info["hips"]
    n = len(hips)
    x0, y0 = hips[0][0], hips[0][1]
    meta = {
        "name": clips.NAME,
        "fps": clips.FPS,
        "frames": n,
        "duration_s": round(n / clips.FPS, 3),
        "reference": {
            "folder": "references/spear_acrobatics",
            "views": {"A": {"frames": [0, 163], "anim_frame_of_first": -clips.F0},
                      "B": {"frames": [164, 333], "anim_frame_of_first": 0}},
            "note": "the folder shows the same take twice; anim frame k = view A frame k - 6 "
                    "= view B frame 164 + k (view A starts 6 frames into the take)",
        },
        "skeleton": {"root": rig.P + "Hips",
                     "spear_bones": rig.SPEAR_FWD + rig.SPEAR_BACK,
                     "spear_length_m": rig.SPEAR_LEN},
        "root_motion": {
            "net_displacement_m": [round(hips[-1][0] - x0, 3), round(hips[-1][1] - y0, 3)],
            "note": "Blender world metres, +x = screen right, +y = away from the reference camera; "
                    "translation lives on mixamorig:Hips (no root bone)",
        },
        "hips_height_m": {"min": min(h[2] for h in hips), "max": max(h[2] for h in hips)},
        "spear_on_floor_windows": windows([lo < 0.02 for lo in info["spear_low"]]),
    }
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def main():
    argv = sys.argv[1:]
    out = os.path.join(scene.ROOT, "assets/animations/combat")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    os.makedirs(out, exist_ok=True)
    arm = scene.setup()
    r = rig.Rig(arm)
    act, info = bake(arm, r)
    export(arm, os.path.join(out, clips.NAME + ".fbx"))
    meta = write_meta(os.path.join(out, clips.NAME + ".json"), info)
    print(f"{clips.NAME}: {meta['frames']} frames, max non-root bone offset "
          f"{info['max_bone_offset'] * arm.matrix_world.to_scale()[0] * 100:.2f} cm, "
          f"spear on floor {meta['spear_on_floor_windows']}")


if __name__ == "__main__":
    main()
