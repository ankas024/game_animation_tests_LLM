"""Bake a Timeline onto the armature as a regular per-frame action."""
import bpy
from mathutils import Quaternion

import rigkit


def bake(arm, rig, T, f0=0, f1=None, name="A_ch02_SwordCombo"):
    f1 = T.end if f1 is None else f1
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = f0, f1
    arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data.action = act
    prev_q = {}
    per_frame = {}
    for f in range(f0, f1 + 1):
        pose = T.sample(f)
        c, Wr, Wp = rig.apply(pose)
        per_frame[f] = c
        for pb in arm.pose.bones:
            q = pb.rotation_quaternion.copy()
            pq = prev_q.get(pb.name)
            if pq is not None and pq.dot(q) < 0:
                q.negate()
                pb.rotation_quaternion = q
            prev_q[pb.name] = q
            pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
            if pb.name == rigkit.P + "Hips":
                pb.keyframe_insert("location", frame=f, group=pb.name)
            if pb.name == rigkit.WEAPON:
                pb.keyframe_insert("scale", frame=f, group=pb.name)
                pb.keyframe_insert("location", frame=f, group=pb.name)
    return act, per_frame
