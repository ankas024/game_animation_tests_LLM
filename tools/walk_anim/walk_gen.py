"""Procedural keyframe generator for the stylized catwalk in references/gippity6.gif.

Run with Blender's Python (bpy):
    python walk_gen.py <in_char.fbx> <out_anim.fbx> [--blend out.blend]

Conventions (armature data space of the Mixamo rig, centimetres):
    +X = character's left, +Y = up, +Z = forward.
The loop is CYCLE frames long at 30 fps; frame 0 is right-foot contact,
frame CYCLE/2 is left-foot contact. Frame CYCLE duplicates frame 0.
"""
import math
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

CYCLE = 32
FPS = 30
P = "mixamorig:"

# ---------------------------------------------------------------- tunables
STEP = 30.0          # one step length (cm), heel-to-heel
CROSS = 3.0          # how far a planted foot lands past the midline (cm)
HIP_DROP = 3.5       # base pelvis lowering so the stance leg can reach (cm)
BOUNCE = 1.6         # pelvis vertical amplitude (cm)
SWAY = 3.5           # pelvis side-to-side over the stance foot (cm)
PELVIS_YAW = 9.0     # degrees, swing-side hip swivels forward
PELVIS_ROLL = 6.0    # degrees, stance hip pops up
CHEST_YAW = 8.0      # degrees, shoulders counter-rotate
STANCE_LEN = 17      # frames of stance per foot (of CYCLE)


def periodic_spline(keys, t, period=CYCLE):
    """Catmull-Rom through (time, value) keys, wrapping at `period`.

    Values may be floats or tuples."""
    keys = sorted(keys)
    n = len(keys)
    t = t % period
    # find segment
    for i in range(n):
        t0 = keys[i][0]
        t1 = keys[(i + 1) % n][0] + (period if i == n - 1 else 0)
        tt = t if t >= t0 else t + period
        if t0 <= tt <= t1:
            break
    pm = keys[(i - 1) % n]
    p0 = keys[i]
    p1 = keys[(i + 1) % n]
    p2 = keys[(i + 2) % n]
    tm = pm[0] - (period if i == 0 else 0)
    t0 = p0[0]
    t1 = p1[0] + (period if i + 1 >= n else 0)
    t2 = p2[0] + (period if i + 2 >= n else 0)
    u = (tt - t0) / (t1 - t0)

    def comp(vm, v0, v1, v2):
        # non-uniform Catmull-Rom tangents
        m0 = (v1 - vm) / (t1 - tm) * (t1 - t0)
        m1 = (v2 - v0) / (t2 - t0) * (t1 - t0)
        u2, u3 = u * u, u * u * u
        return ((2 * u3 - 3 * u2 + 1) * v0 + (u3 - 2 * u2 + u) * m0
                + (-2 * u3 + 3 * u2) * v1 + (u3 - u2) * m1)

    if isinstance(p0[1], (tuple, list)):
        return tuple(comp(pm[1][k], p0[1][k], p1[1][k], p2[1][k]) for k in range(len(p0[1])))
    return comp(pm[1], p0[1], p1[1], p2[1])


def wave(t, peak, amp):
    """Cosine with period CYCLE peaking at frame `peak`."""
    return amp * math.cos(2 * math.pi * (t - peak) / CYCLE)


def wave2(t, peak, amp):
    """Cosine with period CYCLE/2 (once per step) peaking at `peak`."""
    return amp * math.cos(4 * math.pi * (t - peak) / CYCLE)


def rot(axis, deg):
    return Quaternion(Vector(axis), math.radians(deg))


# ---------------------------------------------------------------- foot path
# Local foot time: 0 = this foot's contact. Stance until STANCE_LEN, then swing.
# Swing keys: (time, (x_out, height, z, pitch_deg))  x_out > 0 = towards own side.
SWING_KEYS = [
    (STANCE_LEN + 0.0, None),  # filled from the toe-off pose
    (STANCE_LEN + 3.0, (4.0, 13.0, -0.62 * STEP, 50.0)),
    (STANCE_LEN + 6.0, (7.0, 24.0, -0.55 * STEP, 62.0)),
    (STANCE_LEN + 9.0, (8.0, 31.0, -0.40 * STEP, 68.0)),   # high kick behind
    (STANCE_LEN + 11.0, (5.0, 25.0, -0.10 * STEP, 50.0)),
    (STANCE_LEN + 13.0, (0.0, 9.0, 0.32 * STEP, 15.0)),
]


def stance_z(tl):
    return STEP * (0.5 - tl / (CYCLE / 2))


# Lateral offset added to the swing (x_out units). The reference is asymmetric:
# the right foot flicks out to its own side, the left foot kicks back *behind*
# the stance leg, towards her right.
SWING_X_BIAS = {"Right": 0.0, "Left": -12.0}


def foot_state(tl, toe_rel, x_bias=0.0):
    """Return (x_out, ankle_height, z, pitch_deg, toe_bend) for local time tl.

    toe_rel: rest vector ankle->toe (cm)."""
    tl = tl % CYCLE
    heel_off = STANCE_LEN - 5

    def stance(tl_):
        z = stance_z(tl_)
        pitch = 0.0
        if tl_ > heel_off:
            f = (tl_ - heel_off) / (STANCE_LEN - heel_off)
            pitch = 38.0 * f * f
        # rotate the foot around the toe so the toe stays planted
        r = rot((1, 0, 0), pitch)
        a_rel = -Vector((0, toe_rel.y, toe_rel.z))
        ankle = r @ a_rel - a_rel
        return (-CROSS, ankle.y, z + ankle.z, pitch, pitch)

    if tl <= STANCE_LEN:
        return stance(tl)
    keys = []
    for i, (k, v) in enumerate(SWING_KEYS):
        if v is None:
            s = stance(STANCE_LEN)
            v = s[:4]
        keys.append((k, v))
    # previous/next anchors so the spline joins stance smoothly
    s_prev = stance(STANCE_LEN - 2)[:4]
    s_next = stance(2)[:4]
    s_c = stance(0)[:4]
    keys = [(STANCE_LEN - 2, s_prev)] + keys + [(CYCLE, s_c), (CYCLE + 2, s_next)]
    # simple non-periodic Catmull-Rom over this list
    for i in range(1, len(keys) - 2):
        if keys[i][0] <= tl <= keys[i + 1][0]:
            break
    (tm, vm), (t0, v0), (t1, v1), (t2, v2) = keys[i - 1], keys[i], keys[i + 1], keys[i + 2]
    u = (tl - t0) / (t1 - t0)
    out = []
    for c in range(4):
        m0 = (v1[c] - vm[c]) / (t1 - tm) * (t1 - t0)
        m1 = (v2[c] - v0[c]) / (t2 - t0) * (t1 - t0)
        u2, u3 = u * u, u * u * u
        out.append((2 * u3 - 3 * u2 + 1) * v0[c] + (u3 - 2 * u2 + u) * m0
                   + (-2 * u3 + 3 * u2) * v1[c] + (u3 - u2) * m1)
    toe_bend = max(0.0, 20.0 * (1 - (tl - STANCE_LEN) / 5.0)) if tl < STANCE_LEN + 5 else 0.0
    env = math.sin(math.pi * (tl - STANCE_LEN) / (CYCLE - STANCE_LEN)) ** 2
    return (out[0] + x_bias * env, out[1], out[2], out[3], toe_bend)


# ---------------------------------------------------------------- rig helpers
class Rig:
    def __init__(self, arm_obj):
        self.obj = arm_obj
        self.pb = arm_obj.pose.bones
        self.rest = {b.name: b.matrix_local.copy() for b in arm_obj.data.bones}
        for p in self.pb:
            p.rotation_mode = "QUATERNION"

    def reset(self):
        for p in self.pb:
            p.location = (0, 0, 0)
            p.rotation_quaternion = (1, 0, 0, 0)
            p.scale = (1, 1, 1)

    def update(self):
        bpy.context.view_layer.update()

    def set_delta(self, name, q):
        """Rotate bone by q expressed in (rest) armature axes, relative to its parent."""
        r = self.rest[P + name].to_quaternion()
        self.pb[P + name].rotation_quaternion = r.inverted() @ q @ r

    def head(self, name):
        return self.pb[P + name].head.copy()

    def pose_mat(self, name):
        return self.pb[P + name].matrix.copy()

    def rest_len(self, a, b):
        return (self.rest[P + b].translation - self.rest[P + a].translation).length

    def aim_bone(self, name, head, tail_dir, pole, rest_pole):
        """Set pose matrix so bone points along tail_dir with its bend plane facing pole."""
        rest = self.rest[P + name]
        y0 = (rest.to_3x3() @ Vector((0, 1, 0))).normalized()
        z0 = (rest_pole - y0 * rest_pole.dot(y0)).normalized()
        x0 = y0.cross(z0)
        y1 = tail_dir.normalized()
        z1 = (pole - y1 * pole.dot(y1)).normalized()
        x1 = y1.cross(z1)
        f0 = Matrix((x0, y0, z0)).transposed()
        f1 = Matrix((x1, y1, z1)).transposed()
        r = f1 @ f0.transposed()
        m = (r @ rest.to_3x3()).to_4x4()
        m.translation = head
        self.pb[P + name].matrix = m
        self.update()

    def two_bone_ik(self, upper, lower, end, target, pole, rest_pole):
        a = self.head(upper)
        l1 = self.rest_len(upper, lower)
        l2 = self.rest_len(lower, end)
        d = target - a
        dist = d.length
        dist_c = min(dist, (l1 + l2) * 0.9995)
        dn = d.normalized()
        pp = (pole - dn * pole.dot(dn)).normalized()
        x = (l1 * l1 - l2 * l2 + dist_c * dist_c) / (2 * dist_c)
        h = math.sqrt(max(l1 * l1 - x * x, 0.0))
        knee = a + dn * x + pp * h
        self.aim_bone(upper, a, knee - a, pole, rest_pole)
        end_pt = a + dn * dist_c
        self.aim_bone(lower, self.head(lower), end_pt - self.head(lower), pole, rest_pole)
        return dist - dist_c  # >0 means target unreachable

    def set_world_rot(self, name, q_world_delta):
        """Orient bone = q_world_delta * rest orientation, keeping its posed head."""
        rest = self.rest[P + name]
        m = (q_world_delta.to_matrix() @ rest.to_3x3()).to_4x4()
        m.translation = self.head(name)
        self.pb[P + name].matrix = m
        self.update()


FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


def pose_frame(rig, t):
    rig.reset()
    side = {"Left": 1.0, "Right": -1.0}
    rest = rig.rest
    # local time per foot (right contact at 0, left contact at CYCLE/2)
    tl = {"Right": t % CYCLE, "Left": (t - CYCLE / 2) % CYCLE}

    # ------------------------------------------------------------ pelvis
    # high just before each contact, low ~4 frames after
    bob = periodic_spline([(0, 0.6), (4, -1.0), (9, -0.2), (14, 1.0),
                           (16, 0.6), (20, -1.0), (25, -0.2), (30, 1.0)], t) * BOUNCE
    sway = -SWAY * math.cos(2 * math.pi * (t - 6) / CYCLE)  # over right foot at ~6
    hips_loc = Vector((sway, -HIP_DROP + bob, 0.0))
    yaw = wave(t, 0, PELVIS_YAW)            # right hip forward at right contact
    roll = -wave(t, 6, PELVIS_ROLL)          # right stance -> right hip up
    tilt = 4.0 + wave2(t, 4, 1.5)            # anterior tilt, a touch more after contact
    rig.pb[P + "Hips"].location = rest[P + "Hips"].to_3x3().inverted() @ hips_loc
    rig.set_delta("Hips", rot((0, 1, 0), yaw) @ rot((0, 0, 1), roll) @ rot((1, 0, 0), tilt))

    # ------------------------------------------------------------ spine
    chest_yaw = -wave(t, 2, CHEST_YAW)      # shoulders opposite the hips
    spine_yaw = (chest_yaw - yaw) / 3.0
    spine_roll = -roll / 3.0 + wave(t, 8, 1.2) / 3.0
    for n, k in (("Spine", 1.0), ("Spine1", 1.0), ("Spine2", 1.0)):
        rig.set_delta(n, rot((0, 1, 0), spine_yaw * k) @ rot((0, 0, 1), spine_roll * k)
                      @ rot((1, 0, 0), -1.7 + wave2(t, 6, -0.6)))
    # neck/head keep the gaze forward, slight bob and tilt
    head_yaw = -chest_yaw * 0.8
    rig.set_delta("Neck", rot((0, 1, 0), head_yaw * 0.5) @ rot((1, 0, 0), 2.0) @ rot((0, 0, 1), wave(t, 10, 1.5)))
    rig.set_delta("Head", rot((0, 1, 0), head_yaw * 0.5) @ rot((1, 0, 0), 3.0 + wave2(t, 2, 1.0))
                  @ rot((0, 0, 1), wave(t, 12, 2.5)))
    rig.update()

    # ------------------------------------------------------------ legs
    hips_q = rig.pose_mat("Hips").to_quaternion() @ rest[P + "Hips"].to_quaternion().inverted()
    for s, sx in side.items():
        toe_rel = rest[P + s + "ToeBase"].translation - rest[P + s + "Foot"].translation
        x_out, h, z, pitch, toe_bend = foot_state(tl[s], toe_rel, SWING_X_BIAS[s])
        rest_ankle = rest[P + s + "Foot"].translation
        # x_out < 0 puts the planted foot past the midline (catwalk cross-over)
        target = Vector((sx * x_out, rest_ankle.y + h, z))
        pole = Vector((sx * 0.15, 0.0, 1.0))
        pole = (rot((0, 1, 0), yaw * 0.6) @ pole)
        rig.two_bone_ik(s + "UpLeg", s + "Leg", s + "Foot", target, pole, Vector((0, 0, 1)))
        foot_yaw = sx * 6.0 + yaw * 0.3
        rig.set_world_rot(s + "Foot", rot((0, 1, 0), foot_yaw) @ rot((1, 0, 0), pitch))
        rig.set_delta(s + "ToeBase", rot((1, 0, 0), -toe_bend))
    rig.update()

    # ------------------------------------------------------------ arms
    # arm swing phase: right arm fully forward at frame 22, left at 6
    chest_m = rig.pose_mat("Spine2") @ rest[P + "Spine2"].inverted()
    arm_peak = {"Right": 22.0, "Left": 6.0}
    for s, sx in side.items():
        ph = (t - arm_peak[s]) % CYCLE      # 0 = fully forward
        # hand (wrist) targets in rest armature space; forward hand crosses the belly
        keys = [
            # left fist rides up in front of the chest, right hand crosses lower over the belly
            (0.0, (sx * 5.0, 95.0, 14.0) if s == "Left" else (sx * 0.5, 88.5, 13.0)),
            (5.0, (sx * 12.0, 86.0, 9.0)),
            (10.0, (sx * 22.0, 80.0, -2.0)),
            (16.0, (sx * 26.0, 81.0, -8.0)),   # back and out, hand flared
            (21.0, (sx * 23.0, 80.0, -5.0)),
            (27.0, (sx * 13.0, 84.0, 8.0)),
        ]
        hp = Vector(periodic_spline(keys, ph))
        target = chest_m @ hp
        # small clavicle motion
        rig.set_delta(s + "Shoulder", rot((0, 1, 0), -sx * 4.0 * math.cos(2 * math.pi * ph / CYCLE))
                      @ rot((0, 0, 1), -sx * 2.0))
        rig.update()
        elbow_pole = chest_m.to_3x3() @ Vector((sx * 0.3, -0.3, -1.0))
        rig.two_bone_ik(s + "Arm", s + "ForeArm", s + "Hand", target, elbow_pole, Vector((0, 0, -1)))
        # forearm twist: palm towards the body; wrist flicks out when the arm is back
        back = 0.5 - 0.5 * math.cos(2 * math.pi * ph / CYCLE)   # 0 front .. 1 back
        fa = rig.pose_mat(s + "ForeArm").to_3x3()
        axis = (fa @ Vector((0, 1, 0))).normalized()
        twist = sx * (-35.0 - 25.0 * back)
        q_twist = Quaternion(axis, math.radians(twist))
        m = (q_twist.to_matrix() @ fa).to_4x4()
        m.translation = rig.head(s + "ForeArm")
        rig.pb[P + s + "ForeArm"].matrix = m
        rig.update()
        # wrist: slight flexion forward, extension + outward flick at the back
        rig.set_delta(s + "Hand", rot((0, 0, 1), sx * (-12.0 + 30.0 * back)) @ rot((0, 1, 0), sx * (8.0 - 14.0 * back)))
        # fingers: loose curl in front, more open at the back
        curl = 35.0 - 22.0 * back
        for f in FINGERS:
            for j in (1, 2, 3):
                name = s + "Hand" + f + str(j)
                if P + name not in rig.pb:
                    continue
                if f == "Thumb":
                    rig.set_delta(name, rot((0, 0, 1), -sx * 8.0) @ rot((0, 1, 0), sx * 10.0 * (j > 1)))
                else:
                    spread = {"Index": -4, "Middle": 0, "Ring": 4, "Pinky": 8}[f] * back
                    extra = {"Index": -6, "Middle": 0, "Ring": 4, "Pinky": 8}[f]
                    rig.set_delta(name, rot((0, 0, 1), -sx * (curl + extra) * (1.0 if j == 1 else 0.9))
                                  @ rot((0, 1, 0), sx * spread * (j == 1)))
    rig.update()


def build(char_fbx):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=char_fbx)
    for o in list(bpy.data.objects):
        if o.name == "Icosphere":
            bpy.data.objects.remove(o)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    sc = bpy.context.scene
    sc.name = "ch_02_walk_catwalk"  # FBX take name
    sc.render.fps = FPS
    sc.frame_start = 0
    sc.frame_end = CYCLE
    bpy.context.view_layer.objects.active = arm
    arm.animation_data_create()
    act = bpy.data.actions.new("ch_02_walk_catwalk")
    arm.animation_data.action = act
    rig = Rig(arm)
    for f in range(CYCLE + 1):
        sc.frame_set(f)
        pose_frame(rig, float(f % CYCLE))
        for p in rig.pb:
            p.keyframe_insert("rotation_quaternion", frame=f, group=p.name)
            if p.name == P + "Hips":
                p.keyframe_insert("location", frame=f, group=p.name)
    return arm, act


def export(arm, path):
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE"},
        add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0, armature_nodetype="NULL",
    )


if __name__ == "__main__":
    argv = sys.argv[1:]
    arm, act = build(argv[0])
    if len(argv) > 1 and argv[1] != "-":
        export(arm, argv[1])
    if "--blend" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=argv[argv.index("--blend") + 1])
