"""Author the dodge animation set for ch_02 (Mixamo rig) and export it as FBX.

    pip install bpy          # Blender as a Python module (5.x)
    python3 scripts/build_dodge_anims.py [--preview DIR]

Clips (30 fps, root motion baked into mixamorig:Hips):
    A_Dodge_Stand_R / _L    quick low sidestep dash with a short skid
    A_Dodge_Sprint_R / _L   mid-sprint sideways aerial, legs in a wide straddle

Only the _R clips are authored; the _L clips are their mirror images.

Poses are authored in armature space (+X = character's left, +Y = up,
+Z = forward, centimetres). Bone rotations are Euler (x, y, z) degrees applied
in the parent's frame, composed as Rx @ Ry @ Rz. Right-side bones ("R.*") use
anatomical values: they are mirrored, so the same numbers mean the same
motion on either side (x<0 flexes a limb forward, z<0 lowers an arm,
z>0 spreads a leg). Legs can be driven by a two-bone IK that plants the ball
of the foot ("L.ball") with an absolute foot rotation ("L.frot").
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_FBX = os.path.join(REPO, "assets/skeletal_meshes/characters/ch_02.fbx")
OUT_DIR = os.path.join(REPO, "assets/animations/combat/dodge")
FPS = 30
PRE = "mixamorig:"

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def q(axis, deg):
    return Quaternion(axis, math.radians(deg))


def eul(x=0.0, y=0.0, z=0.0):
    return q(X, x) @ q(Y, y) @ q(Z, z)


def root_rot(pitch, yaw, roll):
    return q(Y, yaw) @ q(Z, roll) @ q(X, pitch)


def foot_rot(pitch, yaw, roll=0.0):
    return q(Y, yaw) @ q(X, pitch) @ q(Z, roll)


def mirror_vec(v):
    return Vector((-v[0], v[1], v[2]))


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------
CENTER = ["Spine", "Spine1", "Spine2", "Neck", "Head"]
SIDED = ["Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase"]
IK_CHANNELS = ["ik", "ball", "frot", "knee"]


def bone_name(key):
    if key in CENTER:
        return PRE + key
    side, part = key.split(".")
    return PRE + ("Left" if side == "L" else "Right") + part


# Static hand shape: a loose combat fist.
FINGER_CURL = {"Index": (30, 55, 40), "Middle": (35, 60, 45),
               "Ring": (40, 62, 45), "Pinky": (45, 62, 45)}
THUMB = {1: (0, -10, -10), 2: (0, 0, -25), 3: (0, 0, -25)}


def finger_rotation(name):
    """Rotation for finger bones (or None), mirrored for the right hand."""
    for side, sign in (("Left", 1), ("Right", -1)):
        if not name.startswith(PRE + side + "Hand"):
            continue
        rest = name[len(PRE + side + "Hand"):]
        for finger, curl in FINGER_CURL.items():
            if rest.startswith(finger) and rest[len(finger):].isdigit():
                i = int(rest[len(finger):])
                if 1 <= i <= 3:
                    return eul(0, 0, -sign * curl[i - 1])
        if rest.startswith("Thumb") and rest[5:].isdigit():
            x, y, z = THUMB.get(int(rest[5:]), (0, 0, 0))
            return eul(x, sign * y, sign * z)
    return None


# --------------------------------------------------------------------------
# Rig
# --------------------------------------------------------------------------
class Rig:
    def __init__(self, arm_obj):
        self.obj = arm_obj
        bones = arm_obj.data.bones
        depth = lambda b: 0 if b.parent is None else 1 + depth(b.parent)
        self.order = sorted(bones, key=depth)
        self.head = {b.name: b.head_local.copy() for b in bones}
        self.rest_q = {b.name: b.matrix_local.to_quaternion() for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.leg = {}
        for side, full in (("L", "Left"), ("R", "Right")):
            hip, knee, ankle, ball = (PRE + full + p for p in ("UpLeg", "Leg", "Foot", "ToeBase"))
            self.leg[side] = dict(
                hip=hip, knee=knee, ankle=ankle, ball=ball,
                la=(self.head[knee] - self.head[hip]).length,
                lb=(self.head[ankle] - self.head[knee]).length,
                ankle_from_ball=self.head[ankle] - self.head[ball],
            )
        self.rest_hips = self.head[PRE + "Hips"].copy()
        self.overreach = []  # filled by leg_ik with (side, stretch) per frame

    def rest_ball(self, side):
        return self.head[self.leg[side]["ball"]].copy()


def frame_from(a, f):
    """Orthonormal basis quaternion with primary axis a and secondary hint f."""
    a = a.normalized()
    f = (f - a * f.dot(a)).normalized()
    m = Matrix((a, f, a.cross(f))).transposed()
    return m.to_quaternion()


def leg_ik(rig, side, hip_pos, hips_q, st, weight):
    """Return absolute rotations (thigh, shin, foot, toe) for a planted leg."""
    L = rig.leg[side]
    sgn = 1 if side == "L" else -1
    pitch, yaw, roll = st[side + ".frot"]
    gf = foot_rot(pitch, sgn * yaw, sgn * roll)
    target = Vector(st[side + ".ball"]) + gf @ L["ankle_from_ball"]
    pole = hips_q @ (q(Y, sgn * st[side + ".knee"]) @ Z)

    d = target - hip_pos
    reach = L["la"] + L["lb"]
    dist = min(max(d.length, 1e-3), reach * 0.999)
    if weight >= 0.5 and d.length / reach > 0.999:
        rig.overreach.append((side, round(d.length / reach, 3)))
    dirv = d.normalized()
    cos_a = (L["la"] ** 2 + dist ** 2 - L["lb"] ** 2) / (2 * L["la"] * dist)
    ang = math.acos(max(-1.0, min(1.0, cos_a)))
    pn = (pole - dirv * pole.dot(dirv)).normalized()
    knee = hip_pos + dirv * (math.cos(ang) * L["la"]) + pn * (math.sin(ang) * L["la"])
    ankle = hip_pos + dirv * dist

    a0 = rig.head[L["knee"]] - rig.head[L["hip"]]
    b0 = rig.head[L["ankle"]] - rig.head[L["knee"]]
    g_thigh = frame_from(knee - hip_pos, pn) @ frame_from(a0, Z).inverted()
    g_shin = frame_from(ankle - knee, pn) @ frame_from(b0, Z).inverted()
    # Toes stay flat on the ground until the heel is well up.
    g_toe = foot_rot(max(0.0, pitch - 35.0), sgn * yaw, sgn * roll)
    return g_thigh, g_shin, gf, g_toe


def solve_pose(rig, st):
    """State dict -> (absolute rotation G, posed head position) per bone."""
    hips = PRE + "Hips"
    G = {hips: root_rot(*st["rot"])}
    pos = {hips: Vector(st["pos"])}
    local = {}
    for key in CENTER:
        local[bone_name(key)] = eul(*st[key])
    for side in "LR":
        for part in SIDED:
            x, y, z = st[side + "." + part]
            if side == "R":
                y, z = -y, -z
            local[bone_name(side + "." + part)] = eul(x, y, z)

    ik_rot = {}
    for b in rig.order[1:]:
        n, par = b.name, rig.parent[b.name]
        pos[n] = pos[par] + G[par] @ (rig.head[n] - rig.head[par])
        d = local.get(n) or finger_rotation(n) or Quaternion()
        g = G[par] @ d
        for side in "LR":
            L = rig.leg[side]
            w = max(0.0, min(1.0, st[side + ".ik"]))
            if n == L["hip"] and w > 0:
                thigh, shin, foot, toe = leg_ik(rig, side, pos[n], G[hips], st, w)
                ik_rot.update({L["hip"]: thigh, L["knee"]: shin, L["ankle"]: foot, L["ball"]: toe})
            if n in ik_rot and n in (L["hip"], L["knee"], L["ankle"], L["ball"]) and w > 0:
                g = g.slerp(ik_rot[n], w)
        G[n] = g
    return G, pos


# --------------------------------------------------------------------------
# Keyframe interpolation (monotone cubic, so holds stay holds)
# --------------------------------------------------------------------------
def pchip_slopes(xs, ys):
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dl = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [dl[0], dl[0]]
    m = [0.0] * n
    for i in range(1, n - 1):
        if dl[i - 1] * dl[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])

    def end(h0, h1, d0, d1):
        s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if s * d0 <= 0:
            return 0.0
        if d0 * d1 <= 0 and abs(s) > abs(3 * d0):
            return 3 * d0
        return s

    m[0] = end(h[0], h[1], dl[0], dl[1])
    m[-1] = end(h[-1], h[-2], dl[-1], dl[-2])
    return m


def pchip_eval(xs, ys, ms, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = max(k for k in range(len(xs) - 1) if xs[k] <= x)
    h = xs[i + 1] - xs[i]
    t = (x - xs[i]) / h
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * ms[i]
            + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * ms[i + 1])


def default_state(rig):
    st = {"pos": tuple(rig.rest_hips), "rot": (0, 0, 0)}
    for k in CENTER:
        st[k] = (0, 0, 0)
    for side in "LR":
        for p in SIDED:
            st[side + "." + p] = (0, 0, 0)
        st[side + ".ik"] = 0.0
        st[side + ".ball"] = tuple(rig.rest_ball(side))
        st[side + ".frot"] = (0, 0, 0)
        st[side + ".knee"] = 0.0
    return st


def channel_tracks(rig, keys):
    """Per-channel key lists. A channel is only keyed on the frames that set it,
    so unrelated keys never introduce holds. The first key starts from the
    defaults, so every channel has a value from frame one."""
    first_frame, first = keys[0]
    tracks = {k: [(first_frame, v)] for k, v in default_state(rig).items()}
    for k, v in first.items():
        if k not in tracks:
            raise KeyError(f"unknown channel {k!r} at frame {first_frame}")
        tracks[k] = [(first_frame, v)]
    for frame, delta in keys[1:]:
        for k, v in delta.items():
            if k not in tracks:
                raise KeyError(f"unknown channel {k!r} at frame {frame}")
            tracks[k].append((frame, v))
    return tracks


def sample(rig, keys):
    chans = {}
    for k, track in channel_tracks(rig, keys).items():
        xs = [f for f, _ in track]
        comps = len(track[0][1]) if isinstance(track[0][1], (tuple, list)) else None
        for c in range(comps) if comps else [None]:
            ys = [float(v if c is None else v[c]) for _, v in track]
            ms = pchip_slopes(xs, ys) if len(xs) > 1 else [0.0]
            chans[(k, c)] = (xs, ys, ms)

    def at(frame):
        st = {}
        for (k, c), (xs, ys, ms) in chans.items():
            val = pchip_eval(xs, ys, ms, frame)
            if c is None:
                st[k] = val
            else:
                st.setdefault(k, [0.0] * 3)[c] = val
        return {k: tuple(v) if isinstance(v, list) else v for k, v in st.items()}

    return at, keys[0][0], keys[-1][0]


def mirror_keys(keys):
    swap = {"L": "R", "R": "L"}
    out = []
    for frame, delta in keys:
        m = {}
        for k, v in delta.items():
            if k == "pos":
                m[k] = (-v[0], v[1], v[2])
            elif k == "rot":
                m[k] = (v[0], -v[1], -v[2])
            elif k in CENTER:
                m[k] = (v[0], -v[1], -v[2])
            else:
                side, part = k.split(".")
                nk = swap[side] + "." + part
                m[nk] = (-v[0], v[1], v[2]) if part == "ball" else v
        out.append((frame, m))
    return out


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------
def legs_ik(lb, rb, lfrot=(0, 14, 0), rfrot=(0, 14, 0), lk=24, rk=24):
    return {"L.ik": 1.0, "R.ik": 1.0, "L.ball": lb, "R.ball": rb,
            "L.frot": lfrot, "R.frot": rfrot, "L.knee": lk, "R.knee": rk}


READY = {
    "pos": (0, 75, 1), "rot": (6, 0, 0),
    "Spine": (4, 0, 0), "Spine1": (3, 0, 0), "Spine2": (3, 0, 0),
    "Neck": (-4, 0, 0), "Head": (-8, 0, 0),
    "L.Shoulder": (0, 0, -4), "R.Shoulder": (0, 0, -4),
    "L.Arm": (-22, 15, -66), "R.Arm": (-22, 15, -66),
    "L.ForeArm": (0, -65, 0), "R.ForeArm": (0, -65, 0),
    "L.Hand": (0, 0, -10), "R.Hand": (0, 0, -10),
    "L.ToeBase": (0, 0, 0), "R.ToeBase": (0, 0, 0),
    **legs_ik((15, 0.1, 9), (-16, 0.1, -5)),
}


def shift(pose, dx):
    """READY pose moved sideways by dx."""
    p = dict(pose)
    p["pos"] = (pose["pos"][0] + dx,) + tuple(pose["pos"][1:])
    for s in "LR":
        b = pose[s + ".ball"]
        p[s + ".ball"] = (b[0] + dx, b[1], b[2])
    return p


DASH = -190.0  # total sideways travel (to the character's right)

DODGE_STAND_R = [
    (0, READY),
    # Load: drop and shift onto the left (push) foot, lean away.
    (2, {"pos": (5, 68, 1), "rot": (12, 0, -8),
         "Spine": (8, 0, -3), "Spine1": (5, 0, -2), "Neck": (-6, 0, 4), "Head": (-12, 0, 8),
         "L.Arm": (-30, 15, -58), "R.Arm": (-38, 15, -62),
         "L.ForeArm": (0, -90, 0), "R.ForeArm": (0, -95, 0),
         "L.ball": READY["L.ball"], "L.frot": READY["L.frot"],
         "R.ball": READY["R.ball"], "R.frot": READY["R.frot"]}),
    # Explode sideways: left leg drives, right foot reaches low.
    (4, {"pos": (-40, 65, 0), "rot": (14, -6, 26),
         "Spine": (10, -4, 4), "Spine1": (6, -4, 3), "Spine2": (4, -2, 2), "Neck": (-6, 0, -8), "Head": (-12, 6, -16),
         "L.Arm": (10, 10, -28), "L.ForeArm": (0, -45, 0), "L.Hand": (0, 0, -25),
         "R.Arm": (-58, 35, -74), "R.ForeArm": (0, -115, 0),
         "L.ball": (13, 0.1, 9), "L.frot": (38, 8, 0),
         "R.ball": (-74, 10, -3), "R.frot": (18, 25, 0), "R.knee": 25}),
    # Skimming flight: hips low, body leaning hard into the dash, trailing leg kicked up.
    (6, {"pos": (-106, 64, -1), "rot": (16, -8, 32),
         "Spine": (10, -6, 4), "Spine1": (6, -6, 3), "Spine2": (4, -4, 2), "Neck": (-6, 0, -10), "Head": (-12, 10, -20),
         "L.Arm": (18, 5, -18), "L.ForeArm": (0, -35, 0),
         "R.Arm": (-62, 38, -76), "R.ForeArm": (0, -120, 0),
         "L.ball": (-46, 26, 8), "L.frot": (70, 8, 0), "L.knee": 0,
         "R.ball": (-150, 9, -4), "R.frot": (12, 25, 0)}),
    # Right foot touches down.
    (8, {"pos": (-150, 61, -1), "rot": (18, -6, 22),
         "L.ball": (-108, 18, 6), "L.frot": (55, 8, 0),
         "R.ball": (-192, 0.1, -5), "R.frot": (8, 20, 0)}),
    # Low skid, left foot sweeps in; right arm drops toward the floor.
    (10, {"pos": (-169, 55, -1), "rot": (22, -4, 12),
          "Spine": (12, -4, 3), "Spine1": (8, -4, 2), "Spine2": (5, -2, 1), "Neck": (-8, 0, -4), "Head": (-14, 6, -10),
          "L.Arm": (25, 5, -14), "L.ForeArm": (0, -30, 0),
          "R.Arm": (-30, 20, -50), "R.ForeArm": (0, -35, 0),
          "L.ball": (-158, 0.1, 8), "L.frot": (25, 8, 0), "L.knee": 10,
          "R.ball": (-200, 0.1, -6), "R.frot": (0, 15, 0), "R.knee": 15}),
    (12, {"pos": (-179, 58, 0), "rot": (18, -2, 5),
          "L.ball": (-174, 0.1, 9), "L.frot": (0, 8, 0),
          "R.ball": (-204, 0.1, -5), "R.frot": (0, 8, 0), "R.knee": 8}),
    # Recover to guard.
    (16, {"pos": (-187, 71, 1), "rot": (8, 0, 0),
          "Spine": (6, 0, 0), "Spine1": (4, 0, 0), "Spine2": (3, 0, 0), "Neck": (-4, 0, 0), "Head": (-9, 0, 0),
          "L.Arm": (-15, 15, -55), "L.ForeArm": (0, -55, 0), "L.Hand": (0, 0, -10),
          "R.Arm": (-28, 15, -64), "R.ForeArm": (0, -75, 0)}),
    (22, shift(READY, DASH)),
    (24, {}),
]


def sprint_pose(x, z, lead, roll=0.0):
    """Sprint stride at foot contact; `lead` is the side whose foot is planted."""
    trail = "L" if lead == "R" else "R"
    sgn = 1 if lead == "L" else -1
    return {
        "pos": (x, 79, z), "rot": (14, 6 * sgn, roll),
        "Spine": (6, -4 * sgn, 0), "Spine1": (4, -4 * sgn, 0), "Spine2": (2, -3 * sgn, 0),
        "Neck": (-8, 0, 0), "Head": (-12, 5 * sgn, 0),
        "L.Shoulder": (0, 0, -4), "R.Shoulder": (0, 0, -4),
        trail + ".Arm": (-55, 10, -72), trail + ".ForeArm": (0, -100, 0),
        lead + ".Arm": (45, 10, -70), lead + ".ForeArm": (0, -70, 0),
        "L.Hand": (0, 0, -10), "R.Hand": (0, 0, -10),
        lead + ".ik": 1.0, trail + ".ik": 1.0,
        lead + ".ball": (x + 9 * sgn, 0.1, z + 20), lead + ".frot": (8, 4, 0), lead + ".knee": 4,
        trail + ".ball": (x - 9 * sgn, 32, z - 38), trail + ".frot": (70, 4, 0), trail + ".knee": 0,
        # FK match for the trailing leg, so blending it out of IK is seamless.
        trail + ".UpLeg": (22, 0, 0), trail + ".Leg": (95, 0, 0), trail + ".Foot": (40, 0, 0),
    }


SPLIT = 72  # leg spread at the top of the flip (degrees per leg)

DODGE_SPRINT_R = [
    # Plant the right foot mid-sprint.
    (0, sprint_pose(0, 0, "R")),
    # Load on the right leg, start tipping right; left leg swings up and out.
    (2, {"pos": (-6, 72, 34), "rot": (10, -4, 16),
         "Spine": (4, 0, 6), "Spine1": (2, 0, 4), "Spine2": (0, 0, 2), "Head": (-10, 0, -6),
         "L.Arm": (-70, 10, -40), "L.ForeArm": (0, -120, 0),
         "R.Arm": (-5, 10, -55), "R.ForeArm": (0, -105, 0),
         "R.ball": (-9, 0.1, 20), "R.frot": (12, 4, 0),
         "L.ik": 0.0, "L.UpLeg": (-35, 0, 35), "L.Leg": (40, 0, 0), "L.Foot": (30, 0, 0)}),
    # Take-off: last push through the right toes.
    (3, {"R.ik": 1.0, "R.ball": (-9, 0.1, 20), "R.frot": (50, 4, 0), "R.knee": 0}),
    (4, {"pos": (-18, 84, 66), "rot": (8, -4, 52),
         "Spine": (0, 0, 6), "Spine1": (0, 0, 4), "Spine2": (-2, 0, 2), "Neck": (-4, 0, -6), "Head": (-6, 0, -16),
         "L.UpLeg": (-15, 0, 62), "L.Leg": (15, 0, 0), "L.Foot": (40, 0, 0),
         "R.Arm": (-65, 10, -38), "R.ForeArm": (0, -128, 0),
         "R.ball": (-12, 12, 34), "R.frot": (70, 4, 0)}),
    # Off the ground; legs open into the straddle, arms tight to the chest.
    (6, {"pos": (-38, 104, 100), "rot": (6, -4, 110),
         "Head": (-4, 0, -12),
         "L.Arm": (-80, 10, -30), "L.ForeArm": (0, -135, 0),
         "R.Arm": (-80, 10, -30), "R.ForeArm": (0, -135, 0),
         "R.ik": 0.0, "R.UpLeg": (-10, 0, 45), "R.Leg": (10, 0, 0), "R.Foot": (40, 0, 0),
         "L.UpLeg": (-10, 0, SPLIT), "L.Leg": (5, 0, 0), "L.Foot": (45, 0, 0)}),
    # Inverted at the apex, full split.
    (9, {"pos": (-70, 120, 150), "rot": (4, -4, 185),
         "Spine": (-4, 0, 0), "Spine1": (-4, 0, 0), "Spine2": (-2, 0, 0), "Head": (-4, 0, -6),
         "R.UpLeg": (-8, 0, SPLIT), "R.Leg": (4, 0, 0)}),
    (12, {"pos": (-100, 102, 198), "rot": (6, -4, 270),
          "Head": (-6, 0, 4),
          "L.ik": 0.0, "L.UpLeg": (-15, 0, 50), "L.Leg": (25, 0, 0), "L.Foot": (20, 0, 0)}),
    # Left foot lands first, under the body; right leg still sweeping round.
    (13, {"L.ik": 0.6, "L.ball": (-118, 6, 220), "L.frot": (30, 4, 0), "L.knee": 10}),
    (14, {"pos": (-118, 80, 232), "rot": (12, -4, 322),
          "Spine": (6, 0, -4), "Spine1": (4, 0, -3), "Spine2": (2, 0, -2), "Neck": (-6, 0, 4), "Head": (-12, 0, 10),
          "L.Arm": (-40, 10, -25), "L.ForeArm": (0, -60, 0),
          "R.Arm": (-30, 10, -20), "R.ForeArm": (0, -40, 0),
          "L.ik": 1.0, "L.ball": (-112, 0.1, 234), "L.frot": (20, 4, 0),
          "R.UpLeg": (-20, 0, 55), "R.Leg": (30, 0, 0)}),
    (13.5, {"R.ik": 0.0}),
    (14.5, {"R.ik": 0.3, "R.ball": (-190, 16, 240), "R.frot": (40, 10, 0)}),
    (15, {"R.ik": 0.5, "R.ball": (-182, 10, 246), "R.frot": (25, 10, 0), "R.knee": 15,
          "R.UpLeg": (-15, 0, 32), "R.Leg": (15, 0, 0), "R.Foot": (15, 0, 0)}),
    # Right foot lands wide, deep catch.
    (16, {"pos": (-132, 63, 262), "rot": (18, -4, 352),
          "Spine": (10, 0, -2), "Spine1": (6, 0, -2), "Spine2": (4, 0, -1), "Neck": (-8, 0, 2), "Head": (-14, 0, 4),
          "L.Arm": (-55, 10, -55), "L.ForeArm": (0, -90, 0),
          "R.Arm": (25, 10, -40), "R.ForeArm": (0, -50, 0),
          "L.ball": (-112, 0.1, 234), "L.frot": (35, 4, 0),
          "R.ik": 1.0, "R.ball": (-178, 0.1, 252), "R.frot": (10, 10, 0)}),
    # Drive out of the catch on the right foot, left leg swings through.
    (17, {"L.ball": (-118, 8, 252), "L.frot": (55, 4, 0)}),
    (18, {"pos": (-140, 68, 290), "rot": (16, 0, 360),
          "R.ball": (-178, 0.1, 252), "R.frot": (35, 6, 0), "R.knee": 6,
          "L.ball": (-134, 18, 292), "L.frot": (40, 4, 0)}),
    (19, {"R.ball": (-172, 6, 264), "R.frot": (55, 4, 0)}),
    (20, {"pos": (-145, 76, 324),
          "L.ball": (-139, 6, 350), "L.frot": (15, 4, 0),
          "R.ball": (-162, 26, 296), "R.frot": (65, 4, 0)}),
    # Back into the sprint, left foot contact.
    (22, sprint_pose(-148, 360, "L", roll=360)),
]

CLIPS = {
    "A_Dodge_Stand_R": DODGE_STAND_R,
    "A_Dodge_Stand_L": mirror_keys(DODGE_STAND_R),
    "A_Dodge_Sprint_R": DODGE_SPRINT_R,
    "A_Dodge_Sprint_L": mirror_keys(DODGE_SPRINT_R),
}


# --------------------------------------------------------------------------
# Blender I/O
# --------------------------------------------------------------------------
def load_character():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.fbx(filepath=CHAR_FBX)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    return arm


def bake(rig, name, keys):
    arm = rig.obj
    at, f0, f1 = sample(rig, keys)
    act = bpy.data.actions.new(name)
    arm.animation_data_create()
    arm.animation_data.action = act
    hips = PRE + "Hips"
    prev = {}
    lowest = 1e9
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    for f in range(int(f0), int(f1) + 1):
        rig.overreach = []
        G, pos = solve_pose(rig, at(f))
        if rig.overreach:
            print(f"  frame {f}: leg overstretched {rig.overreach}")
        for pb in arm.pose.bones:
            n = pb.name
            par = rig.parent[n]
            d = G[n] if par is None else G[par].inverted() @ G[n]
            r = rig.rest_q[n]
            basis = r.inverted() @ d @ r
            if n in prev and prev[n].dot(basis) < 0:
                basis.negate()
            prev[n] = basis
            pb.rotation_quaternion = basis
            pb.keyframe_insert("rotation_quaternion", frame=f, group=n)
            if n == hips:
                pb.location = r.inverted() @ (pos[n] - rig.head[n])
                pb.keyframe_insert("location", frame=f, group=n)
        for s in "LR":
            L = rig.leg[s]
            lowest = min(lowest, pos[L["ball"]].y, pos[L["ankle"]].y)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = int(f0), int(f1)
    print(f"{name}: frames {int(f0)}-{int(f1)}, lowest foot joint {lowest:.1f}cm")
    return act


def export_fbx(rig, act, path):
    arm = rig.obj
    arm.animation_data.action = act
    bpy.context.scene.name = act.name  # FBX take name
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE"},
        add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
    )


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="render preview frames into this directory")
    ap.add_argument("--only", help="only build clips whose name contains this")
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args(argv)

    arm = load_character()
    bpy.context.scene.render.fps = FPS
    rig = Rig(arm)
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, keys in CLIPS.items():
        if args.only and args.only not in name:
            continue
        act = bake(rig, name, keys)
        if not args.no_export:
            export_fbx(rig, act, os.path.join(OUT_DIR, name + ".fbx"))
        if args.preview:
            import preview_render
            preview_render.render(arm, name, args.preview)


if __name__ == "__main__":
    main()
