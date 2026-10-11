"""
Validation for the exported sword combo / idle FBX files.

Runs with the Blender Python module (`pip install bpy`, Blender 5.1):

    python -I -m pytest tests/animation/test_sword_combo.py      (or)
    python -I tests/animation/test_sword_combo.py

Each test re-imports the exported FBX into an empty scene and checks it the
way an engine importer would see it.
"""
import json
import math
import os
import sys

try:
    import pytest
    bpy = pytest.importorskip("bpy")
except ImportError:          # plain `python test_sword_combo.py` without pytest
    import bpy
from mathutils import Vector  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMBO = os.path.join(REPO, "assets", "animations", "combat", "A_ch02_SwordCombo.fbx")
EVENTS = os.path.join(REPO, "assets", "animations", "combat", "A_ch02_SwordCombo.events.json")
IDLE = os.path.join(REPO, "assets", "animations", "idle", "A_ch02_Idle_Loop.fbx")
SWORD = os.path.join(REPO, "assets", "skeletal_meshes", "props", "SM_Sword_Placeholder.fbx")
SOURCE = os.path.join(REPO, "assets", "skeletal_meshes", "characters", "ch_02.fbx")
P = "mixamorig:"


def _load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # anim_offset=0: keep FBX time 0 at frame 0 (Blender defaults to frame 1)
    bpy.ops.import_scene.fbx(filepath=path, anim_offset=0.0)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    return arm


def _world(arm, bone, local=Vector((0, 0, 0))):
    pb = arm.pose.bones[bone]
    return arm.matrix_world @ pb.matrix @ local


def _body_bones(arm):
    """Skip the skeleton's leaf '*_end' helpers: the importer gives them
    metres-long display lengths, so they amplify tiny rotations."""
    return [pb.name for pb in arm.pose.bones if not pb.name.endswith("_end")]


def _action_range(arm):
    act = arm.animation_data.action
    return int(round(act.frame_range[0])), int(round(act.frame_range[1]))


def test_skeleton_matches_source():
    src = _load(SOURCE)
    src_bones = {b.name: (src.matrix_world @ b.head_local) for b in src.data.bones}
    arm = _load(COMBO)
    names = {b.name for b in arm.data.bones}
    assert set(src_bones) <= names, "combo skeleton lost bones"
    assert names - set(src_bones) == {"weapon_r"}
    assert arm.data.bones["weapon_r"].parent.name == P + "RightHand"
    for n, h in src_bones.items():
        h2 = arm.matrix_world @ arm.data.bones[n].head_local
        assert (h2 - h).length < 1e-3, f"rest pose moved for {n}"


def test_combo_timing_and_events():
    arm = _load(COMBO)
    a, b = _action_range(arm)
    data = json.load(open(EVENTS))
    assert (a, b) == (data["frame_start"], data["frame_end"])
    assert data["fps"] == 60
    assert len(data["curves"]["SwordMaterialize"]) == b - a + 1
    names = [e["name"] for e in data["events"]]
    for need in ("summon_start", "hit_1", "hit_2", "hit_5_impact", "dismiss_start", "end"):
        assert need in names


def test_sword_appears_and_vanishes():
    arm = _load(COMBO)
    a, b = _action_range(arm)
    sc = bpy.context.scene

    def sword_scale(f):
        sc.frame_set(f)
        return arm.pose.bones["weapon_r"].matrix.to_scale().x

    assert sword_scale(a) < 0.01, "sword visible before the summon"
    assert sword_scale(150) > 0.99, "sword missing mid-combo"
    assert sword_scale(b) < 0.01, "sword still visible at the end"


def test_feet_stay_above_floor_and_loop_closes():
    arm = _load(COMBO)
    a, b = _action_range(arm)
    sc = bpy.context.scene
    lowest = 1e9
    for f in range(a, b + 1, 2):
        sc.frame_set(f)
        for s in ("Left", "Right"):
            for bn in ("Foot", "ToeBase", "Toe_End", "Leg"):
                lowest = min(lowest, _world(arm, P + s + bn).z)
    assert lowest > -0.015, f"bone below the floor ({lowest:.3f} m)"
    # last frame returns to the first frame's pose (blends straight into idle)
    sc.frame_set(a)
    first = {n: _world(arm, n) for n in _body_bones(arm)}
    sc.frame_set(b)
    worst = max((_world(arm, n) - p).length for n, p in first.items() if n != "weapon_r")
    assert worst < 0.01, f"end pose differs from start pose by {worst:.3f} m"


def test_idle_loop_is_seamless_and_matches_combo():
    arm = _load(IDLE)
    a, b = _action_range(arm)
    sc = bpy.context.scene
    sc.frame_set(a)
    p0 = {n: _world(arm, n) for n in _body_bones(arm)}
    sc.frame_set(b)
    p1 = {n: _world(arm, n) for n in _body_bones(arm)}
    # the last frame should sit one frame "before" the first: compare with
    # the motion of a regular frame step
    step = max((p1[n] - p0[n]).length for n in p0)
    assert step < 0.004, f"idle loop seam jump {step:.4f} m"
    combo = _load(COMBO)
    ca, _ = _action_range(combo)
    bpy.context.scene.frame_set(ca)
    worst = max((_world(combo, n) - p0[n]).length for n in p0 if n in combo.pose.bones)
    assert worst < 0.005, f"combo start differs from idle loop start by {worst:.4f} m"


def test_sword_prop():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=SWORD)
    ob = next(o for o in bpy.data.objects if o.type == 'MESH')
    dims = sorted(ob.dimensions)
    assert 0.8 < dims[-1] < 1.0, f"unexpected sword length {dims[-1]:.3f}"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
