"""
NieR-inspired sword combo for ch_02 (60 fps).

    idle -> summon (iai-style draw, sword materialises along the arc)
    -> rising slash -> descending slash -> 360 spin slash
    -> launcher (rising cut + jump) -> front-flip plunge -> impact
    -> twirl + blood flick -> back-hop -> sword dissolves -> idle

Coordinates: character space, x right, y forward, z up (metres).
Sword frames are authored as (blade direction, edge direction) vectors;
`swing()` derives a leading edge from the arc automatically.
"""
import math
from mathutils import Vector, Matrix
from timeline import Timeline

FPS = 60


def V(*a):
    return Vector(a)


def rotz(v, deg):
    return Matrix.Rotation(math.radians(deg), 3, 'Z') @ Vector(v)


# ---------------------------------------------------------------------------
# reusable poses
# ---------------------------------------------------------------------------
IDLE_BODY = dict(
    hips_x=0.010, hips_y=0.022, hips_z=0.838, hips_yaw=-6.0, hips_pitch=2.0, hips_roll=-3.0,
    sp_twist=6.0, sp_bend=1.5, sp_side=2.5,
    hd_yaw=3.0, hd_pitch=-1.0, hd_roll=-2.0, hd_abs=1.0,
    lsh_up=0.0, rsh_up=0.0, lsh_fwd=0.0, rsh_fwd=0.0,
    rh_r=0.296, lh_r=0.280, rh_space=0.0, lh_space=0.0,
    r_pole_x=0.5, r_pole_y=-0.5, r_pole_z=-1.0,
    l_pole_x=-0.5, l_pole_y=-0.5, l_pole_z=-1.0,
    r_curl=0.38, l_curl=0.38, l_spread=0.0,
)
IDLE_FEET = {"L": (-0.112, 0.080, 12.0), "R": (0.098, 0.035, -9.0)}
IDLE_RDIR = V(0.30, 0.02, -1.0)
IDLE_LDIR = V(-0.30, 0.04, -1.0)
IDLE_SW = (V(0.05, 0.93, -0.40), V(0.15, 0.0, -1.0))       # relaxed hanging hand
IDLE_LH = (V(-0.10, 0.10, -1.0), V(0.05, 1.0, 0.0))        # fingers down, thumb fwd


def put(T, f, pose=None, ease=None, rdir=None, ldir=None, sw=None, lh=None):
    if pose:
        T.key(f, ease, **pose)
    if rdir is not None:
        T.rdir(f, rdir, ease=ease)
    if ldir is not None:
        T.ldir(f, ldir, ease=ease)
    if sw is not None:
        T.sword(f, sw[0], sw[1], ease=ease)
    if lh is not None:
        T.lhand(f, lh[0], lh[1], ease=ease)


def swing(T, keys, roll=0.0):
    """keys: [(frame, blade_dir, grip_dir, grip_r, ease, edge_override|None)]
    The edge leads along the blade's arc (central differences)."""
    blades = [Vector(k[1]).normalized() for k in keys]
    n = len(keys)
    for i, k in enumerate(keys):
        f, b, gd, r, ease = k[:5]
        edge = k[5] if len(k) > 5 else None
        b = blades[i]
        if ease is None and 0 < i < n - 1:
            ease = "cr"
        if edge is None:
            if i == 0:
                t = blades[1] - b
            elif i == n - 1:
                t = b - blades[i - 1]
            else:
                t = blades[i + 1] - blades[i - 1]
            edge = t - t.dot(b) * b
            if roll:
                edge = Matrix.Rotation(math.radians(roll), 3, b) @ edge
        T.sword(f, b, edge, ease=ease)
        if gd is not None:
            T.rdir(f, gd, ease=ease)
        if r is not None:
            T.key(f, ease, rh_r=r)


class Feet:
    """Keeps planted feet glued: every plant is keyed at its start and end."""

    def __init__(self, T):
        self.T = T
        self.state = {}

    def _k(self, side, f, x, y, z, yaw, lift, space=0.0, ease=None):
        p = "lf" if side == "L" else "rf"
        self.T.key(f, ease, **{p + "_x": x, p + "_y": y, p + "_z": z, p + "_yaw": yaw,
                               p + "_lift": lift, p + "_space": space})
        self.state[side] = dict(x=x, y=y, z=z, yaw=yaw, lift=lift, space=space)

    def plant(self, side, f, x=None, y=None, yaw=None, lift=None, ease=None):
        s = dict(self.state.get(side, {}))
        x = s["x"] if x is None else x
        y = s["y"] if y is None else y
        yaw = s["yaw"] if yaw is None else yaw
        lift = s.get("lift", 0.0) if lift is None else lift
        self._k(side, f, x, y, 0.0, yaw, lift, 0.0, ease)

    def hold(self, side, f):
        s = self.state[side]
        self._k(side, f, s["x"], s["y"], s["z"], s["yaw"], s["lift"], s["space"])

    def step(self, side, f0, f1, x, y, yaw, h=0.06, lift_end=0.0, toe_off=20.0, ease=None):
        s = self.state[side]
        self.hold(side, f0)
        fm = f0 + (f1 - f0) * 0.45
        self._k(side, fm, (s["x"] + x) / 2, (s["y"] + y) / 2, h, (s["yaw"] + yaw) / 2, toe_off * 0.5)
        self._k(side, f1, x, y, 0.0, yaw, lift_end, 0.0, ease)

    def air(self, side, f, x, y, z, yaw, lift=0.0, space=0.0, ease=None):
        self._k(side, f, x, y, z, yaw, lift, space, ease)


# ---------------------------------------------------------------------------
def build():
    T = Timeline(FPS)
    T.offsets = {"hips_": -1.5, "sp_": -0.7, "hd_": 2.0, "lh": 2.5, "l_": 2.5,
                 "sw_az": 0.8, "sw_el": 0.8, "sw_roll": 0.8}
    ev = {}
    F = Feet(T)

    def idle_pose(f, ease=None, feet=True):
        put(T, f, IDLE_BODY, ease, IDLE_RDIR, IDLE_LDIR, IDLE_SW, IDLE_LH)
        if feet:
            for s, (x, y, yaw) in IDLE_FEET.items():
                F.plant(s, f, x, y, yaw, 0.0)

    # ======================================================================
    # 0. idle
    # ======================================================================
    idle_pose(0)
    T.key(0, sw_mat=0.0, sw_spin=0.0, sw_off=0.0)
    idle_pose(30)

    # ======================================================================
    # 1. summon -- iai draw from an invisible scabbard (f30-84)
    # ======================================================================
    put(T, 44, dict(hips_x=-0.012, hips_y=0.030, hips_z=0.800, hips_yaw=20, hips_pitch=7, hips_roll=1,
                    sp_twist=14, sp_bend=10, sp_side=-2, hd_yaw=-4, hd_pitch=12, hd_roll=0,
                    rh_r=0.285, r_curl=0.75, r_pole_x=1.0, r_pole_y=0.6, r_pole_z=-0.4,
                    lh_r=0.235, l_curl=0.65, l_pole_x=-1.0, l_pole_y=-0.4, l_pole_z=-0.6),
        rdir=V(-0.78, 0.30, -0.58), ldir=V(-0.35, 0.35, -0.85),
        lh=(V(0.35, 0.9, -0.3), V(0.2, 0.0, 1.0)))
    F.plant("R", 30)
    F.plant("L", 30)
    F.plant("R", 42, yaw=-14, lift=4)
    F.step("L", 44, 53, -0.135, 0.215, 10.0, h=0.05)
    F.step("R", 47, 56, 0.170, -0.170, -36.0, h=0.03, lift_end=9.0)
    ev["summon_start"] = 46
    swing(T, [
        (44, V(-0.30, -1.0, -0.22), None, None, None, V(0.0, 0.0, 1.0)),
        (50, V(-0.55, 1.0, -0.05), V(-0.10, 1.0, -0.30), 0.300, None),
        (55, V(1.0, -0.35, 0.05), V(0.88, 0.45, -0.06), 0.312, "out"),
        (63, V(0.75, -0.85, -0.15), V(0.86, 0.10, -0.18), 0.300, None, V(0.0, -0.25, -1.0)),
    ])
    put(T, 50, dict(hips_yaw=2, hips_z=0.785, hips_pitch=6, hips_y=0.04, sp_twist=0, sp_bend=7, hd_pitch=4,
                    r_curl=1.0, r_pole_x=0.8, r_pole_y=0.2, r_pole_z=-1.0))
    put(T, 55, dict(hips_x=0.02, hips_y=0.02, hips_z=0.765, hips_yaw=-26, hips_pitch=8, hips_roll=3,
                    sp_twist=-12, sp_bend=7, sp_side=-5, hd_yaw=0, hd_pitch=0, hd_roll=0,
                    r_pole_x=0.3, r_pole_y=-0.4, r_pole_z=-1.0,
                    lh_r=0.27, l_curl=0.08, l_spread=0.7, l_pole_x=-0.3, l_pole_y=-0.2, l_pole_z=-1.0),
        ease="out", ldir=V(-0.95, -0.35, -0.20), lh=(V(-1.0, -0.3, -0.10), V(0.0, 0.2, 1.0)))
    # flourish: one turn of the sword in the hand right after the draw
    T.key(56, sw_spin=0.0, sw_off=0.0)
    T.key(58, sw_off=0.035)
    T.key(58, sw_spin=0.0, ease="inout")
    T.key(68, sw_spin=-360.0, sw_off=0.035)
    T.key(71, sw_off=0.0)
    T.key(46, sw_mat=0.0, ease="out")
    T.key(58, sw_mat=1.0)
    ev["summon_flash"] = 55
    put(T, 63, dict(hips_yaw=-22, sp_twist=-4, hips_z=0.755))

    READY = dict(hips_x=0.02, hips_y=0.0, hips_z=0.745, hips_yaw=-20, hips_pitch=10, hips_roll=2,
                 sp_twist=12, sp_bend=11, sp_side=-4, hd_yaw=0, hd_pitch=-4, hd_roll=0,
                 rh_r=0.30, r_pole_x=0.5, r_pole_y=-0.6, r_pole_z=-1.0,
                 lh_r=0.25, l_curl=0.12, l_spread=0.5, l_pole_x=-0.8, l_pole_y=-0.3, l_pole_z=-0.7)
    READY_SW = (V(0.40, -1.0, -0.55), V(0.0, -0.45, -1.0))
    READY_RDIR = V(0.60, -0.38, -0.72)
    put(T, 76, READY, rdir=READY_RDIR, ldir=V(-0.20, 1.0, -0.12), sw=READY_SW,
        lh=(V(-0.15, 0.65, 0.75), V(1.0, 0.25, 0.0)))
    F.hold("L", 76)
    F.hold("R", 76)

    # ======================================================================
    # 2. rising diagonal slash, right foot steps in (f84-110)
    # ======================================================================
    put(T, 86, dict(READY, hips_z=0.735, hips_yaw=-30, sp_twist=-2, sp_bend=13, hips_y=-0.02),
        rdir=V(0.55, -0.55, -0.62), sw=(V(0.30, -1.0, -0.75), V(0.1, 0.6, -0.8)))
    s1 = [V(0.35, -0.70, -0.62), V(0.45, 0.55, -0.70), V(0.15, 1.0, 0.05), V(-0.55, 0.45, 0.70),
          V(-0.65, -0.20, 0.75)]
    swing(T, [
        (91, s1[0], V(0.50, -0.30, -0.72), 0.30, None),
        (94, s1[1], V(0.32, 0.65, -0.62), 0.31, None),
        (96, s1[2], V(0.05, 1.0, -0.08), 0.32, None),
        (99, s1[3], V(-0.30, 0.70, 0.50), 0.31, None),
        (104, s1[4], V(-0.40, 0.35, 0.72), 0.28, None),
    ])
    put(T, 91, dict(hips_yaw=-28, hips_y=0.0, hips_z=0.74, sp_twist=-4))
    put(T, 96, dict(hips_x=0.02, hips_y=0.18, hips_z=0.72, hips_yaw=5, hips_pitch=12, hips_roll=-2,
                    sp_twist=8, sp_bend=8, sp_side=4, hd_pitch=-2,
                    r_pole_x=0.7, r_pole_y=-0.3, r_pole_z=-0.8))
    put(T, 100, dict(hips_x=0.0, hips_y=0.25, hips_z=0.735, hips_yaw=28, hips_pitch=6, hips_roll=-3,
                     sp_twist=18, sp_bend=-2, sp_side=6, hd_yaw=-6, hd_pitch=-6, hd_roll=4,
                     r_pole_x=1.0, r_pole_y=0.2, r_pole_z=-0.5,
                     lh_r=0.28, l_curl=0.1, l_spread=0.8, l_pole_x=-0.2, l_pole_y=0.3, l_pole_z=-1.0),
        ease="out", ldir=V(-0.65, -0.70, -0.30), lh=(V(-0.55, -0.80, -0.20), V(0.3, -0.2, 1.0)))
    put(T, 105, dict(hips_y=0.26, hips_z=0.74, hips_yaw=30, sp_twist=20, sp_bend=-3))
    F.hold("R", 89)
    F.step("R", 89, 97, 0.105, 0.430, -12.0, h=0.07)
    F.plant("L", 92, lift=6)
    F.plant("L", 100, yaw=28, lift=22)
    ev["hit_1"] = 96

    # ======================================================================
    # 3. descending diagonal slash (backhand), left foot steps in (f108-128)
    # ======================================================================
    s2 = [V(-0.50, -0.45, 0.80), V(-0.35, 0.65, 0.65), V(0.10, 1.0, -0.05), V(0.55, 0.40, -0.75),
          V(0.55, -0.45, -0.75)]
    swing(T, [
        (110, s2[0], V(-0.45, 0.25, 0.80), 0.27, None),
        (113, s2[1], V(-0.35, 0.75, 0.45), 0.30, None),
        (115, s2[2], V(0.0, 1.0, -0.05), 0.32, None),
        (117, s2[3], V(0.45, 0.55, -0.62), 0.31, None),
        (124, s2[4], V(0.65, -0.15, -0.68), 0.30, None),
    ])
    put(T, 110, dict(hips_yaw=32, sp_twist=22, sp_bend=-4, hips_z=0.745, hips_y=0.26,
                     r_pole_x=1.0, r_pole_y=0.5, r_pole_z=0.2))
    put(T, 115, dict(hips_x=0.0, hips_y=0.38, hips_z=0.725, hips_yaw=5, hips_pitch=12, hips_roll=2,
                     sp_twist=0, sp_bend=10, sp_side=-2, hd_yaw=0, hd_pitch=0, hd_roll=0,
                     r_pole_x=0.8, r_pole_y=-0.2, r_pole_z=-0.8))
    put(T, 119, dict(hips_x=0.01, hips_y=0.44, hips_z=0.72, hips_yaw=-30, hips_pitch=14, hips_roll=3,
                     sp_twist=-14, sp_bend=12, sp_side=-6, hd_yaw=4, hd_pitch=-4, hd_roll=-3,
                     r_pole_x=0.4, r_pole_y=-0.8, r_pole_z=-0.8,
                     lh_r=0.27, l_curl=0.05, l_spread=0.9, l_pole_x=-0.5, l_pole_y=-0.6, l_pole_z=-0.5),
        ease="out", ldir=V(-0.90, 0.40, 0.05), lh=(V(-0.9, 0.3, 0.30), V(0.0, 1.0, 0.0)))
    put(T, 126, dict(hips_yaw=-34, sp_twist=-16, hips_z=0.725, hips_y=0.45))
    F.hold("L", 111)
    F.step("L", 111, 118, -0.125, 0.640, 14.0, h=0.06)
    F.plant("R", 113, lift=8)
    F.plant("R", 120, yaw=-38, lift=16)
    ev["hit_2"] = 116

    # ======================================================================
    # 4. 360 spin slash, pivot on the left foot (f126-166)
    # ======================================================================
    pivot = V(-0.125, 0.640, 0.0)
    r_rel = V(0.105, 0.430, 0.0) - pivot          # right foot relative to pivot
    h_rel = V(0.01, 0.45, 0.0) - pivot            # hips relative to pivot
    spin_keys = [  # frame, body turn (deg, +left), sword rel az, hand rel az
        (130, -50, 105, 95),
        (135, 0, 70, 55),
        (139, 80, 45, 40),
        (143, 170, 40, 35),
        (147, 260, 40, 35),
        (151, 330, 20, 25),
        (156, 375, -65, -45),
    ]
    for i, (f, turn, rel_sw, rel_h) in enumerate(spin_keys):
        face_az = -turn
        h = pivot + rotz(h_rel, turn + 34.0) if turn > -40 else V(0.02, 0.45, 0.0)
        hz = 0.735 if i in (0, len(spin_keys) - 1) else 0.75
        el_sw = -18 if i == 0 else (-6 if i < len(spin_keys) - 1 else -22)
        swa = math.radians(face_az + rel_sw)
        blade = V(math.sin(swa) * math.cos(math.radians(el_sw)), math.cos(swa) * math.cos(math.radians(el_sw)),
                  math.sin(math.radians(el_sw)))
        ha = math.radians(face_az + rel_h)
        gd = V(math.sin(ha), math.cos(ha), -0.35 if 0 < i < len(spin_keys) - 1 else -0.55)
        # spinning left -> blade sweeps towards decreasing az -> edge "left" of blade
        edge = V(-math.cos(swa), math.sin(swa), 0.0)
        mid = 0 < i < len(spin_keys) - 1
        T.sword(f, blade, edge, ease="cr" if mid else None)
        T.rdir(f, gd, ease="cr" if mid else None)
        T.key(f, "cr" if mid else None, hips_x=h.x, hips_y=h.y, hips_yaw=turn + (-8 if 0 < i < 6 else 0))
        T.key(f, rh_r=0.315 if 0 < i < len(spin_keys) - 1 else 0.30,
              hips_z=hz,
              sp_twist=-12 if i == 0 else (10 if i < len(spin_keys) - 1 else 20),
              sp_bend=8, sp_side=0, hips_pitch=10, hips_roll=-4 if 0 < i < 6 else 0,
              r_pole_x=0.3, r_pole_y=-0.9, r_pole_z=-0.6)
        # head spots: lags then whips round ahead of the body
        hd = {130: -10, 135: 20, 139: 50, 143: 215, 147: 300, 151: 345, 156: 360}[f]
        T.key(f, hd_yaw=hd, hd_pitch=0, hd_roll=0)
    # left arm pulled in tight during the spin, flung out at the end
    put(T, 133, dict(lh_r=0.17, l_curl=0.5, l_spread=0.0, l_pole_x=-0.4, l_pole_y=-0.8, l_pole_z=-0.6),
        ldir=V(0.25, 0.85, -0.45))
    put(T, 150, dict(lh_r=0.17), ldir=rotz(V(0.25, 0.85, -0.45), 330))
    put(T, 158, dict(lh_r=0.27, l_curl=0.08, l_spread=0.9), ldir=V(0.4, -0.85, -0.35),
        lh=(V(0.3, -1.0, -0.2), V(0.0, 0.0, 1.0)))
    # feet: left pivots on the ball, right foot circles round
    F.plant("L", 128, lift=4)
    F.plant("L", 131, lift=12)
    for f, yaw in ((135, 20), (139, 94), (143, 184), (147, 274)):
        F.plant("L", f, yaw=yaw, lift=14)
    F.plant("L", 150, yaw=14 + 330, lift=14)
    F.plant("L", 156, yaw=14 + 352, lift=0)
    F.plant("R", 128)
    F.plant("R", 131, lift=25)
    for f, ang, z in ((135, 40, 0.07), (139, 120, 0.10), (143, 200, 0.10), (147, 270, 0.08),
                      (151, 320, 0.04)):
        p = pivot + rotz(r_rel, ang)
        F.air("R", f, p.x, p.y, z, -38 + ang, 20, ease="cr")
    def spin_layer(f, p, a=130.0, b=156.0, ramp=3.0):
        """exact circular paths for hips / swinging foot during the spin"""
        if not (a <= f <= b):
            return
        w = min(1.0, (f - a) / ramp, (b - f) / ramp)
        w = w * w * (3 - 2 * w)
        hc = pivot + rotz(h_rel, p["hips_yaw"] + 8.0 * w + 34.0)
        p["hips_x"] += (hc.x - p["hips_x"]) * w
        p["hips_y"] += (hc.y - p["hips_y"]) * w
        if p["rf_z"] > 0.002:
            fc = pivot + rotz(r_rel, p["rf_yaw"] + 38.0)
            wf = w * min(1.0, p["rf_z"] / 0.03)
            p["rf_x"] += (fc.x - p["rf_x"]) * wf
            p["rf_y"] += (fc.y - p["rf_y"]) * wf
    T.layers.append(spin_layer)
    pl = pivot + rotz(r_rel, 345)
    F.plant("R", 155, pl.x, pl.y, -38 + 350, 6)
    F.plant("R", 162, lift=0)
    put(T, 164, dict(hips_x=-0.02, hips_y=0.50, hips_z=0.735, hips_yaw=360 + 12, hips_pitch=10,
                     sp_twist=18, hd_yaw=360, rh_r=0.30), rdir=V(-0.75, 0.55, -0.45),
        sw=(V(-0.80, 0.45, -0.40), V(-0.3, -0.6, -0.5)))
    ev["hit_3a"] = 136
    ev["hit_3b"] = 155

    # ======================================================================
    # 5. launcher: crouch, rising cut, jump (f164-188)
    # ======================================================================
    lx, ly = F.state["L"]["x"], F.state["L"]["y"]
    rx, ry = F.state["R"]["x"], F.state["R"]["y"]
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    put(T, 172, dict(hips_x=cx, hips_y=cy - 0.02, hips_z=0.62, hips_yaw=380, hips_pitch=22, hips_roll=0,
                     sp_twist=12, sp_bend=16, sp_side=0, hd_yaw=360, hd_pitch=-14,
                     r_pole_x=-0.2, r_pole_y=-0.6, r_pole_z=-1.0, rh_r=0.30,
                     lh_r=0.26, l_curl=0.1, l_spread=0.5, l_pole_x=-0.6, l_pole_y=-0.5, l_pole_z=-0.6),
        ldir=V(-0.7, -0.5, -0.5))
    lau = [V(-0.85, -0.35, -0.42), V(-0.25, 0.85, -0.45), V(0.0, 0.75, 0.66), V(0.15, -0.25, 0.96),
           V(0.20, -0.75, 0.62)]
    swing(T, [
        (172, lau[0], V(-0.62, 0.38, -0.68), 0.29, None),
        (176, lau[1], V(-0.15, 0.95, -0.55), 0.31, None),
        (179, lau[2], V(0.05, 0.75, 0.55), 0.31, None),
        (182, lau[3], V(0.15, 0.10, 0.98), 0.30, None),
        (186, lau[4], V(0.20, -0.10, 0.97), 0.27, None),
    ])
    for s in ("L", "R"):
        F.plant(s, 166)
        F.plant(s, 172, lift=8)
        F.plant(s, 176, lift=35)
    put(T, 176, dict(hips_y=cy + 0.03, hips_z=0.70, hips_pitch=10, sp_bend=2, hd_pitch=-6,
                     r_pole_x=0.4, r_pole_y=0.3, r_pole_z=-1.0))
    put(T, 180, dict(hips_y=cy + 0.06, hips_z=0.95, hips_pitch=-6, hips_yaw=365, sp_twist=-4, sp_bend=-10,
                     hd_pitch=-14, lh_r=0.27, r_pole_x=1.0, r_pole_y=0.0, r_pole_z=0.0),
        ldir=V(-0.8, -0.3, 0.3), lh=(V(-0.8, -0.3, 0.4), V(0.0, 0.0, 1.0)))
    ev["hit_4"] = 179
    ev["jump_takeoff"] = 178
    # airborne: feet switch to hips space
    F.air("L", 180, -0.10, 0.03, 0.12, 6, 30, space=1.0)
    F.air("R", 180, 0.10, -0.02, 0.10, -6, 30, space=1.0)

    # ======================================================================
    # 6. front flip + plunge (f184-206)
    # ======================================================================
    # switch sword / left hand to chest space while the body is upright
    put(T, 184, dict(hips_x=cx, hips_y=cy + 0.10, hips_z=1.16, hips_pitch=0, hips_yaw=360, hips_roll=0,
                     sp_twist=0, sp_bend=-6, sp_side=0, hd_abs=1.0, hd_yaw=360, hd_pitch=-8,
                     rh_space=0.0, lh_space=0.0))
    T.key(187, rh_space=1.0, lh_space=1.0, hd_abs=0.0)
    T.key(184, hd_abs=1.0)
    # chest-space sword overhead, blade back (keyed as if upright)
    flip_sw = (V(0.10, -0.80, 0.60), V(0.0, -0.6, -0.8))
    put(T, 187, dict(hips_z=1.22, hips_y=cy + 0.14, hips_pitch=24, sp_bend=10, hd_pitch=10, hd_yaw=0,
                     rh_r=0.25, r_pole_x=0.8, r_pole_y=0.0, r_pole_z=0.1,
                     lh_r=0.17, l_curl=0.6, l_spread=0.0, l_pole_x=-0.5, l_pole_y=-0.5, l_pole_z=-0.5),
        rdir=V(0.20, 0.20, 0.96), sw=flip_sw, ldir=V(0.2, 0.8, -0.5))
    F.air("L", 187, -0.10, 0.22, 0.38, 0, 10, space=1.0)
    F.air("R", 187, 0.10, 0.20, 0.36, 0, 10, space=1.0)
    # flip: tucked, rotate 360 forward about the hips
    for f, p, z, y in ((190, 95, 1.26, 0.20), (193, 190, 1.24, 0.27), (196, 280, 1.16, 0.33),
                       (199, 345, 1.02, 0.38)):
        T.key(f, "cr", hips_pitch=p, hips_y=cy + y)
        T.key(f, hips_z=z, sp_bend=24, hd_pitch=20)
        T.rdir(f, V(0.20, 0.35, 0.92))
        T.sword(f, V(0.10, -0.55, 0.83), V(0.0, -0.8, -0.55))
        T.ldir(f, V(0.2, 0.8, -0.5))
        T.key(f, rh_r=0.24, lh_r=0.17)
        F.air("L", f, -0.10, 0.30, 0.48, 0, 12, space=1.0)
        F.air("R", f, 0.10, 0.28, 0.46, 0, 12, space=1.0)
    # out of the flip: extend, sword high over the head, about to slam
    put(T, 201, dict(hips_pitch=362, hips_z=0.96, hips_y=cy + 0.40, sp_bend=-14, hd_pitch=-10,
                     rh_r=0.27, r_pole_x=0.9, r_pole_y=0.2, r_pole_z=0.2, lh_r=0.26),
        rdir=V(0.10, -0.10, 1.0), sw=(V(0.0, -0.70, 0.72), V(0.0, 0.7, 0.7)),
        ldir=V(-0.8, -0.4, 0.2), lh=(V(-0.8, -0.4, 0.3), V(0.0, 0.0, 1.0)))
    F.air("L", 201, -0.12, 0.02, 0.30, 0, 25, space=1.0)
    F.air("R", 201, 0.12, 0.22, 0.32, 0, 10, space=1.0)
    T.key(203, hips_z=0.70)
    T.key(202, rh_space=1.0, lh_space=1.0, hd_abs=0.0)
    T.key(204, rh_space=0.0, lh_space=0.0, hd_abs=1.0)
    # plunge: vertical downward cut into the ground, superhero landing
    land_y = cy + 0.42
    swing(T, [
        (201, V(0.0, -0.70, 0.72), None, None, None, V(0.0, 0.7, 0.7)),
        (203, V(0.05, 0.55, 0.85), V(0.15, 0.55, 0.65), 0.30, None),
        (205, V(0.25, 1.0, -0.35), V(0.32, 0.92, -0.45), 0.31, None),
        (207, V(0.28, 0.80, -0.60), V(0.36, 0.72, -0.62), 0.30, "out"),
    ])
    put(T, 205, dict(hips_x=cx + 0.01, hips_y=land_y, hips_z=0.475, hips_pitch=362 + 26, hips_yaw=362,
                     hips_roll=0, sp_twist=-6, sp_bend=22, sp_side=0, hd_yaw=360, hd_pitch=-24, hd_roll=0,
                     r_pole_x=0.7, r_pole_y=-0.4, r_pole_z=-0.6,
                     lh_r=0.28, l_curl=0.05, l_spread=1.0, l_pole_x=-0.6, l_pole_y=0.2, l_pole_z=-0.8),
        ease="out", ldir=V(-0.75, -0.55, -0.35), lh=(V(-0.7, -0.6, -0.30), V(0.0, 0.3, 1.0)))
    F.air("L", 203, -0.12, land_y - 0.30, 0.10, 6, 35, space=0.0)
    F.air("R", 203, 0.12, land_y + 0.21, 0.11, -6, 0, space=0.0)
    F.plant("L", 205, -0.13, land_y - 0.36, 8, 44)
    F.plant("R", 205, 0.12, land_y + 0.24, -6, 0)
    ev["hit_5_impact"] = 205
    # impact recoil + hold
    put(T, 209, dict(hips_z=0.445, hips_pitch=362 + 30, sp_bend=26, hd_pitch=-26))
    put(T, 222, dict(hips_z=0.46, hips_pitch=362 + 27, sp_bend=24, hd_pitch=-20),
        rdir=V(0.38, 0.72, -0.60), sw=(V(0.30, 0.80, -0.58), V(0.0, -0.60, -0.80)))
    for s in ("L", "R"):
        F.hold(s, 222)

    # ======================================================================
    # 7. rise, twirl, blood flick (f222-268)
    # ======================================================================
    ry_ = F.state["R"]["y"]
    put(T, 236, dict(hips_x=0.03, hips_y=ry_ - 0.18, hips_z=0.79, hips_pitch=362 + 6, hips_yaw=360 - 10,
                     hips_roll=-2, sp_twist=-4, sp_bend=4, sp_side=2, hd_yaw=360, hd_pitch=-6,
                     rh_r=0.30, r_pole_x=0.6, r_pole_y=-0.4, r_pole_z=-1.0,
                     lh_r=0.28, l_curl=0.3, l_spread=0.2, l_pole_x=-0.5, l_pole_y=-0.5, l_pole_z=-1.0),
        rdir=V(0.55, 0.45, -0.70), sw=(V(0.30, 1.0, 0.15), V(0.0, 0.3, -1.0)),
        ldir=V(-0.35, 0.05, -1.0), lh=IDLE_LH)
    F.step("L", 226, 236, -0.11, ry_ - 0.16, 10, h=0.05)
    F.plant("R", 228, lift=0)
    # twirl: two full spins of the sword in the hand beside the right leg
    # slopes match at the joins: 2*180/5 = 540/7.5 = 72 deg per frame
    T.key(235, sw_off=0.0)
    T.key(238, sw_spin=-360.0, ease="in", sw_off=0.04)
    T.key(243, sw_spin=-540.0, ease="lin")
    T.key(248, sw_spin=-900.0, ease="out")
    T.key(253, sw_spin=-1080.0, sw_off=0.04)
    T.key(257, sw_off=0.0)
    put(T, 243, dict(rh_r=0.30), rdir=V(0.75, 0.45, -0.38), sw=(V(0.30, 1.0, 0.0), V(0.0, 0.2, -1.0)))
    put(T, 248, dict(rh_r=0.29), rdir=V(0.72, 0.50, -0.36), sw=(V(0.25, 1.0, 0.1), V(0.0, 0.2, -1.0)))
    ev["twirl"] = 238
    # flick: snap forward-up then down-right (chiburi)
    swing(T, [
        (254, V(0.25, 1.0, 0.35), V(0.50, 0.55, -0.55), 0.30, None),
        (256, V(0.55, 0.90, 0.15), V(0.75, 0.45, -0.30), 0.31, None),
        (258, V(0.70, 0.10, -0.70), V(0.80, 0.10, -0.55), 0.31, "snap"),
        (268, V(0.60, -0.10, -0.78), V(0.75, 0.0, -0.62), 0.30, None),
    ])
    put(T, 254, dict(hips_yaw=360 + 4, sp_twist=6, hips_z=0.80))
    put(T, 260, dict(hips_yaw=360 - 18, sp_twist=-10, hips_z=0.775, hips_roll=3, sp_side=-3, hd_pitch=-8,
                     hd_yaw=360 + 4), ease="out")
    ev["flick"] = 258

    # ======================================================================
    # 8. back hop (f268-300)
    # ======================================================================
    hy0 = F.state["R"]["y"]
    for s in ("L", "R"):
        F.plant(s, 268)
        F.plant(s, 274, lift=14)
    put(T, 274, dict(hips_z=0.72, hips_pitch=362 + 12, hips_y=ry_ - 0.16, sp_bend=10, hd_pitch=-10,
                     lh_r=0.25, l_curl=0.3, l_pole_x=-0.6, l_pole_y=-0.6, l_pole_z=-0.6),
        ldir=V(-0.45, -0.35, -0.85), lh=IDLE_LH)
    put(T, 279, dict(hips_z=0.86, hips_pitch=362 - 4, hips_y=ry_ - 0.30, sp_bend=-4, lh_r=0.26, l_curl=0.15),
        ldir=V(-0.45, 0.65, -0.15), lh=(V(-0.3, 0.8, 0.2), V(0.7, 0.0, 0.7)))
    F.air("L", 281, -0.12, (ry_ - 0.16 + 0.12) / 2 - 0.22, 0.12, 10, 30)
    F.air("R", 281, 0.13, (hy0 + 0.0) / 2 - 0.18, 0.14, -20, 30)
    put(T, 284, dict(hips_z=0.93, hips_y=(ry_ + 0.02) / 2 - 0.10, sp_bend=2), rdir=V(0.65, -0.20, -0.72),
        sw=(V(0.50, -1.0, -0.40), V(0.0, -0.35, -1.0)), ldir=V(-0.75, 0.35, -0.35),
        lh=(V(-0.7, 0.3, -0.2), V(0.2, 0.3, 1.0)))
    F.plant("L", 290, -0.125, 0.12, 10, 0)
    F.plant("R", 291, 0.140, -0.02, -24, 0)
    put(T, 291, dict(hips_x=0.01, hips_y=0.04, hips_z=0.72, hips_pitch=362 + 10, hips_yaw=360 - 14,
                     sp_bend=8, sp_twist=4, hd_pitch=-4, lh_r=0.27, l_curl=0.3), ease="out",
        ldir=V(-0.55, 0.15, -0.80))
    put(T, 302, dict(lh_r=0.28, l_curl=0.38, l_pole_x=-0.5, l_pole_y=-0.5, l_pole_z=-1.0),
        ldir=IDLE_LDIR, lh=IDLE_LH)
    ev["hop_land"] = 290

    # ======================================================================
    # 9. dismiss: sword dissolves, back to idle (f296-380)
    # ======================================================================
    put(T, 300, dict(hips_z=0.79, hips_pitch=362 + 4, hips_yaw=360 - 10, sp_bend=3, sp_twist=2,
                     hd_pitch=-2, hd_yaw=360, rh_r=0.30, r_curl=1.0, r_pole_x=0.6, r_pole_y=-0.3, r_pole_z=-1.0),
        rdir=V(0.85, 0.10, -0.52), sw=(V(0.85, 0.30, -0.42), V(0.2, 0.1, -1.0)))
    ev["dismiss_start"] = 304
    T.key(304, sw_mat=1.0)
    T.key(326, sw_mat=0.0, ease="inout")
    T.key(306, hd_yaw=360 - 22, hd_pitch=8, hd_roll=-4)
    T.key(324, hd_yaw=360 - 18, hd_pitch=6, hd_roll=-3)
    put(T, 318, dict(rh_r=0.30, r_curl=0.95), rdir=V(0.80, 0.12, -0.58), sw=(V(0.85, 0.35, -0.40), V(0.2, 0.1, -1.0)))
    put(T, 330, dict(r_curl=0.2), ease="out")
    # settle back into the idle pose (same feet as frame 0)
    F.step("R", 316, 330, IDLE_FEET["R"][0], IDLE_FEET["R"][1], IDLE_FEET["R"][2], h=0.03)
    F.step("L", 334, 346, IDLE_FEET["L"][0], IDLE_FEET["L"][1], IDLE_FEET["L"][2], h=0.025)
    put(T, 340, dict(hips_z=0.83, hips_pitch=362 + 2, hips_yaw=360 - 6, hips_x=0.02, hips_y=0.035))
    idle_pose(352, feet=False)
    idle_pose(380, feet=False)
    for s in ("L", "R"):
        F.hold(s, 380)
    ev["end"] = 380

    T.events = ev
    T.end = 380
    return T


# ---------------------------------------------------------------------------
def build_idle(length=240):
    """Seamless idle loop that starts/ends on the combo's idle pose.
    All sinusoids divide the loop length, and are zero at frame 0."""
    T = Timeline(FPS)
    F = Feet(T)
    for f in (0, length):
        put(T, f, IDLE_BODY, None, IDLE_RDIR, IDLE_LDIR, IDLE_SW, IDLE_LH)
        for s, (x, y, yaw) in IDLE_FEET.items():
            F.plant(s, f, x, y, yaw, 0.0)
        T.key(f, sw_mat=0.0, sw_spin=0.0, sw_off=0.0)
    two_pi = 2 * math.pi

    def breathe(f, p):
        b = math.sin(two_pi * f / (length / 2))          # two breaths per loop
        w = math.sin(two_pi * f / length)                # slow weight shift
        p["sp_bend"] -= 1.1 * b
        p["lsh_up"] += 1.4 * b
        p["rsh_up"] += 1.4 * b
        p["hips_z"] += 0.0025 * math.sin(two_pi * f / (length / 2) + 0.6) - 0.0025 * math.sin(0.6)
        p["hips_x"] += 0.006 * w
        p["hips_roll"] -= 1.2 * w
        p["sp_side"] += 1.0 * w
        p["hd_yaw"] += 2.5 * math.sin(two_pi * f / length * 1.0 + 0.0)
        p["hd_pitch"] += 0.8 * b
        p["lh_az"] = p.get("lh_az", 0.0) - 1.5 * w
        p["rh_az"] = p.get("rh_az", 0.0) + 1.5 * w
    T.layers.append(breathe)
    T.events = {"loop_start": 0, "loop_end": length}
    T.end = length
    return T
