"""
Build + export all game assets for the sword combo.

    python -I export_assets.py            (bpy module, Blender 5.1)

Writes (repo relative):
    assets/animations/combat/A_ch02_SwordCombo.fbx
    assets/animations/combat/A_ch02_SwordCombo.events.json
    assets/animations/combat/source/A_ch02_SwordCombo.blend
    assets/animations/idle/A_ch02_Idle_Loop.fbx
    assets/skeletal_meshes/props/SM_Sword_Placeholder.fbx
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import scene_util as su  # noqa: E402
import rigkit  # noqa: E402
import sword  # noqa: E402
import combo  # noqa: E402
import bake  # noqa: E402

REPO = su.REPO
OUT_COMBAT = os.path.join(REPO, "assets", "animations", "combat")
OUT_IDLE = os.path.join(REPO, "assets", "animations", "idle")
OUT_PROPS = os.path.join(REPO, "assets", "skeletal_meshes", "props")

FBX_ARGS = dict(
    use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE', axis_forward='-Z', axis_up='Y',
    add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X',
    use_armature_deform_only=False, armature_nodetype='NULL', mesh_smooth_type='FACE',
    bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
    bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True,
    bake_anim_step=1.0, bake_anim_simplify_factor=0.0, path_mode='STRIP',
)


def strip_missing_textures():
    """The source FBX references a texture that isn't in the repo; drop the
    dangling image nodes so exported files don't carry a broken path."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        for n in list(m.node_tree.nodes):
            if n.type == 'TEX_IMAGE' and (n.image is None or not n.image.has_data):
                m.node_tree.nodes.remove(n)
    for img in list(bpy.data.images):
        if not img.has_data:
            bpy.data.images.remove(img)


def select_only(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_combo():
    arm, meshes = su.load_character()
    strip_missing_textures()
    rig = rigkit.Rig(arm)
    rig.ensure_weapon_bone()
    sw = sword.build_skinned(arm, rig)
    T = combo.build()
    act, per_frame = bake.bake(arm, rig, T, name="A_ch02_SwordCombo")
    sc = bpy.context.scene
    sc.frame_set(0)
    os.makedirs(OUT_COMBAT, exist_ok=True)
    select_only([arm] + meshes + [sw])
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_COMBAT, "A_ch02_SwordCombo.fbx"), **FBX_ARGS)

    # events / curves sidecar
    fps = combo.FPS
    ev = dict(T.events)
    ev["summon_end"] = ev["summon_flash"] + 3
    ev["dismiss_end"] = ev["dismiss_start"] + 22
    events = [{"name": k, "frame": int(v), "time": round(v / fps, 4)}
              for k, v in sorted(ev.items(), key=lambda kv: kv[1])]
    curve = [round(per_frame[f]["sw_mat"], 4) for f in range(0, T.end + 1)]
    data = {
        "animation": "A_ch02_SwordCombo",
        "fps": fps, "frame_start": 0, "frame_end": T.end,
        "duration_s": round(T.end / fps, 4),
        "skeleton": "ch_02 Mixamo rig + weapon_r (child of mixamorig:RightHand)",
        "root_motion": "Translation lives on mixamorig:Hips. The combo leaves and returns to the "
                       "same spot/facing (net displacement ~0), so it plays in place.",
        "notes": "weapon_r is scaled to ~0 while the sword does not exist; drive a dissolve "
                 "material with curves.SwordMaterialize (0 = gone, 1 = solid).",
        "events": events,
        "windows": {
            "summon": [ev["summon_start"], ev["summon_end"]],
            "dismiss": [ev["dismiss_start"], ev["dismiss_end"]],
            "airborne": [ev["jump_takeoff"], ev["hit_5_impact"]],
        },
        "curves": {"SwordMaterialize": curve},
    }
    with open(os.path.join(OUT_COMBAT, "A_ch02_SwordCombo.events.json"), "w") as fh:
        json.dump(data, fh, indent=1)

    # editable source
    src = os.path.join(OUT_COMBAT, "source")
    os.makedirs(src, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(src, "A_ch02_SwordCombo.blend"), compress=True)
    return T


def export_idle():
    arm, meshes = su.load_character()
    strip_missing_textures()
    rig = rigkit.Rig(arm)
    rig.ensure_weapon_bone()
    T = combo.build_idle()
    # bake 0..end-1 so the loop doesn't contain a duplicated frame
    bake.bake(arm, rig, T, 0, T.end - 1, name="A_ch02_Idle_Loop")
    os.makedirs(OUT_IDLE, exist_ok=True)
    select_only([arm] + meshes)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_IDLE, "A_ch02_Idle_Loop.fbx"), **FBX_ARGS)


def export_sword_prop():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = sword.build_mesh("SM_Sword_Placeholder")
    for m in sword.make_materials():
        me.materials.append(m)
    ob = bpy.data.objects.new("SM_Sword_Placeholder", me)
    bpy.context.scene.collection.objects.link(ob)
    os.makedirs(OUT_PROPS, exist_ok=True)
    select_only([ob])
    args = dict(FBX_ARGS)
    args.update(bake_anim=False, object_types={'MESH'})
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_PROPS, "SM_Sword_Placeholder.fbx"), **args)


if __name__ == "__main__":
    export_sword_prop()
    export_idle()
    export_combo()
    print("exported")
