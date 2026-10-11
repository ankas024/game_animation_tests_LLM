"""
NieR-inspired sword combo for ch_02 (60 fps), v2.

    idle -> coil -> iai draw (sword materialises along the arc)
    -> figure-8 flow: forehand lunge cut -> backhand passing cut
    -> 300 deg spinning cut with an arabesque leg -> crouch
    -> rising launcher -> jump, front flip at the apex -> diving slam
    -> rise into a fencer's point -> chiburi wheel, triple twirl
    -> sword dissolves -> idle

The combo travels about 2 m forward and ends in the idle pose on the new
spot, facing the original direction.

Coordinates: character space, x right, y forward, z up (metres).
Sword motion is authored as Catmull-Rom paths of (blade direction, grip
direction, grip radius) sampled every frame; the cutting edge is derived
from the path so it always leads.  The timeline post-process (springs +
low-pass, see timeline.py) adds follow-through and removes any remaining
velocity kinks.
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


# ---------------------------------------------------------------------------
# splines
# ---------------------------------------------------------------------------
class Spline:
    """Non-uniform Catmull-Rom through (t, value) keys (floats or Vectors).
    ends[i] True -> zero velocity at that end, False -> one-sided slope."""

    def __init__(self, ts, ps, ends=(True, True)):
        self.t = [float(t) for t in ts]
        self.p = ps
        n = len(ps)
        m = []
        for i in range(n):
            if 0 < i < n - 1:
                m.append((ps[i + 1] - ps[i - 1]) / (self.t[i + 1] - self.t[i - 1]))
            elif n == 1:
                m.append(ps[0] * 0.0)
            elif i == 0:
                m.append(ps[0] * 0.0 if ends[0] else (ps[1] - ps[0]) / (self.t[1] - self.t[0]))
            else:
                m.append(ps[-1] * 0.0 if ends[1] else (ps[-1] - ps[-2]) / (self.t[-1] - self.t[-2]))
        self.m = m

    def at(self, t):
        ts, ps, m = self.t, self.p, self.m
        if t <= ts[0]:
            return ps[0], m[0] * 0.0
        if t >= ts[-1]:
            return ps[-1], m[-1] * 0.0
        i = 0
        while ts[i + 1] < t:
            i += 1
        h = ts[i + 1] - ts[i]
        u = (t - ts[i]) / h
        h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
        h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        d00, d10 = 6 * u * u - 6 * u, 3 * u * u - 4 * u + 1
        d01, d11 = -6 * u * u + 6 * u, 3 * u * u - 2 * u
        v = ps[i] * h00 + m[i] * (h * h10) + ps[i + 1] * h01 + m[i + 1] * (h * h11)
        dv = (ps[i] * d00 + ps[i + 1] * d01) / h + m[i] * d10 + m[i + 1] * d11
        return v, dv


def blade_path(T, keys, ends=(True, True), edge0=None, s_ref=0.05):
    """Key the sword every frame along a smooth path.

    keys: [(frame, blade_dir, grip_dir, grip_r[, roll_deg])]
    The edge leads the blade's motion; while the blade is (nearly) still it
    keeps its last edge.  `roll` turns the edge about the blade (presenting
    the flat, wrist turnover in a loop).  Returns the final (blade, edge)."""
    ts = [k[0] for k in keys]
    B = Spline(ts, [Vector(k[1]).normalized() for k in keys], ends)
    G = Spline(ts, [Vector(k[2]).normalized() for k in keys], ends)
    Rr = Spline(ts, [float(k[3]) for k in keys], ends)
    Ro = Spline(ts, [float(k[4]) if len(k) > 4 else 0.0 for k in keys], (True, True))
    f0, f1 = int(round(ts[0])), int(round(ts[-1]))
    rows = []
    for f in range(f0, f1 + 1):
        b, db = B.at(f)
        L = max(b.length, 1e-6)
        bn = b / L
        v = (db - db.dot(bn) * bn) / L
        rows.append((f, bn, v))
    e_prev = None
    if edge0 is not None:
        e_prev = Vector(edge0)
    else:
        for f, bn, v in rows:
            if v.length > s_ref * 0.5:
                e_prev = v.normalized()
                break
        if e_prev is None:
            e_prev = Vector((0, 0, 1))
    out = None
    for f, bn, v in rows:
        sp = v.length
        w = min(1.0, sp / s_ref)
        w = w * w * (3 - 2 * w)
        ep = e_prev - e_prev.dot(bn) * bn
        if ep.length < 1e-6:
            ep = v.copy()
        ep.normalize()
        e = ep * (1 - w) + (v.normalized() if sp > 1e-9 else ep) * w
        if e.length < 1e-6:
            e = ep
        e.normalize()
        e_prev = e
        roll = Ro.at(f)[0]
        e_out = Matrix.Rotation(math.radians(roll), 3, bn) @ e if roll else e
        g, _ = G.at(f)
        r, _ = Rr.at(f)
        T.sword(f, bn, e_out)
        T.rdir(f, g.normalized())
        T.key(f, rh_r=r)
        out = (bn, e_out)
    return out


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

    def step(self, side, f0, f1, x, y, yaw, h=0.06, lift_end=0.0, toe_off=20.0, ease=None, peak=0.45):
        s = self.state[side]
        self.hold(side, f0)
        fm = f0 + (f1 - f0) * peak
        self._k(side, fm, s["x"] + (x - s["x"]) * 0.42, s["y"] + (y - s["y"]) * 0.42, h,
                (s["yaw"] + yaw) / 2, toe_off * 0.5)
        self._k(side, f1, x, y, 0.0, yaw, lift_end, 0.0, ease)

    def air(self, side, f, x, y, z, yaw, lift=0.0, space=0.0, ease=None):
        self._k(side, f, x, y, z, yaw, lift, space, ease)


# ---------------------------------------------------------------------------
def build(rig=None):
    T = Timeline(FPS)
    # overlap: hips lead, spine slightly, sword blade drags the hand a hair,
    # the head and free arm trail (springs add the follow-through on top)
    T.offsets = {"hips_": -1.5, "sp_": -0.7, "hd_": 1.0, "lh": 1.0, "l_": 1.0,
                 "sw_az": 0.8, "sw_el": 0.8, "sw_roll": 0.8}
    T.default_sigma = 1.0
    T.sigma = {"hips_": 1.3, "lf_": 0.8, "rf_": 0.8, "sw_mat": 0.0, "sw_spin": 0.5,
               "rh_r": 1.3, "lh_r": 1.3}
    sp = (0.42, 0.55)
    T.springs = {"sp_twist": sp, "sp_bend": sp, "sp_side": sp,
                 "hd_yaw": (0.45, 0.6), "hd_pitch": (0.45, 0.6), "hd_roll": (0.45, 0.6),
                 "lh_az": (0.36, 0.5), "lh_el": (0.36, 0.5),
                 "lhd_az": (0.45, 0.6), "lhd_el": (0.45, 0.6), "lhd_roll": (0.45, 0.6),
                 "l_curl": (0.4, 0.6), "l_spread": (0.4, 0.6),
                 "lsh_": (0.4, 0.55), "rsh_": (0.4, 0.55),
                 "hips_pitch": (0.55, 0.65), "hips_roll": (0.55, 0.65)}
    ev = {}
    F = Feet(T)

    def idle_pose(f, ox=0.0, oy=0.0, ease=None, feet=True):
        body = dict(IDLE_BODY, hips_x=IDLE_BODY["hips_x"] + ox, hips_y=IDLE_BODY["hips_y"] + oy)
        put(T, f, body, ease, IDLE_RDIR, IDLE_LDIR, IDLE_SW, IDLE_LH)
        if feet:
            for s, (x, y, yaw) in IDLE_FEET.items():
                F.plant(s, f, x + ox, y + oy, yaw, 0.0)

    # ======================================================================
    # 0. idle
    # ======================================================================
    idle_pose(0)
    T.key(0, sw_mat=0.0, sw_spin=0.0, sw_off=0.0)
    idle_pose(10)

    # ======================================================================
    # 1. coil (f10-27): weight onto the left leg, body winds left, the right
    #    hand reaches across to an invisible scabbard at the left hip
    # ======================================================================
    put(T, 27, dict(hips_x=-0.035, hips_y=0.03, hips_z=0.745, hips_yaw=30, hips_pitch=14, hips_roll=-4,
                    sp_twist=24, sp_bend=14, sp_side=-4, hd_yaw=-4, hd_pitch=8, hd_roll=3, hd_abs=1.0,
                    rsh_fwd=10, r_curl=0.85, r_pole_x=1.0, r_pole_y=0.6, r_pole_z=-0.4,
                    lh_r=0.22, l_curl=0.6, l_spread=0.0, l_pole_x=-1.0, l_pole_y=-0.4, l_pole_z=-0.6),
        ldir=V(-0.40, 0.30, -0.86), lh=(V(0.35, 0.9, -0.3), V(0.2, 0.0, 1.0)))
    F.plant("L", 10)
    F.plant("R", 10)
    F.plant("R", 24, yaw=-24, lift=22)
    F.plant("L", 24, yaw=18, lift=0)

    # ======================================================================
    # 2. iai draw (f27-44): explosive uncoil to the right, right foot lunges
    #    out wide, horizontal backhand across the front; the blade forms
    #    along the arc
    # ======================================================================
    ev["summon_start"] = 29
    T.key(29, sw_mat=0.0)
    T.key(41, sw_mat=1.0)
    ev["summon_flash"] = 38
    F.step("R", 28, 37, 0.36, 0.46, -50.0, h=0.08, toe_off=24)
    F.plant("L", 33, yaw=0, lift=10)
    F.plant("L", 40, yaw=-6, lift=26)
    put(T, 33, dict(hips_x=0.06, hips_y=0.16, hips_z=0.70, hips_yaw=2, hips_pitch=18, hips_roll=2,
                    sp_twist=2, sp_bend=14, sp_side=1, hd_yaw=-6, hd_pitch=6, hd_roll=0,
                    rsh_fwd=0, r_curl=1.0), ease="cr")
    put(T, 41, dict(hips_x=0.17, hips_y=0.28, hips_z=0.615, hips_yaw=-46, hips_pitch=22, hips_roll=7,
                    sp_twist=-30, sp_bend=12, sp_side=6, hd_yaw=-14, hd_pitch=6, hd_roll=-3,
                    r_pole_x=0.3, r_pole_y=-0.6, r_pole_z=-0.8,
                    lh_r=0.28, l_curl=0.05, l_spread=0.9, l_pole_x=-0.3, l_pole_y=0.2, l_pole_z=-1.0),
        ldir=V(-0.85, -0.45, -0.10), lh=(V(-1.0, -0.4, -0.05), V(0.0, 0.2, 1.0)))

    # ======================================================================
    # 3. figure-8 into cut 1 (f44-70): left foot closes up behind, the blade
    #    loops up behind the right shoulder, then a big forehand diagonal
    #    (high right -> low left) on a long right-foot lunge
    # ======================================================================
    F.step("L", 43, 51, 0.04, 0.32, -30.0, h=0.06, lift_end=10)
    put(T, 50, dict(hips_x=0.14, hips_y=0.38, hips_z=0.735, hips_yaw=-46, hips_pitch=6, hips_roll=-2,
                    sp_twist=-24, sp_bend=-12, sp_side=-8, hd_yaw=-8, hd_pitch=-4, hd_roll=4,
                    r_pole_x=1.0, r_pole_y=-0.2, r_pole_z=0.2,
                    lh_r=0.27, l_curl=0.1, l_spread=0.6, l_pole_x=-0.6, l_pole_y=-0.2, l_pole_z=-0.8),
        ldir=V(0.10, 1.0, 0.10), lh=(V(0.1, 1.0, 0.3), V(0.0, 0.2, 1.0)))
    F.step("R", 52, 60, 0.16, 0.98, -12.0, h=0.10, toe_off=18)
    F.plant("L", 56, yaw=-20, lift=24)
    put(T, 56, dict(hips_x=0.10, hips_y=0.55, hips_z=0.68, hips_yaw=-30, hips_pitch=18, hips_roll=0,
                    sp_twist=-10, sp_bend=6, sp_side=-2), ease="cr")
    put(T, 61, dict(hips_x=0.06, hips_y=0.71, hips_z=0.590, hips_yaw=12, hips_pitch=30, hips_roll=-4,
                    sp_twist=18, sp_bend=22, sp_side=-6, hd_yaw=4, hd_pitch=10, hd_roll=-2,
                    r_pole_x=0.6, r_pole_y=-0.5, r_pole_z=-0.8))
    put(T, 68, dict(hips_x=0.04, hips_y=0.76, hips_z=0.575, hips_yaw=26, hips_pitch=32, hips_roll=-5,
                    sp_twist=32, sp_bend=24, sp_side=-6, hd_yaw=10, hd_pitch=12, hd_roll=-4,
                    lh_r=0.28, l_curl=0.05, l_spread=1.0, l_pole_x=-0.4, l_pole_y=-0.6, l_pole_z=0.2),
        ldir=V(-0.70, -0.60, 0.35), lh=(V(-0.7, -0.6, 0.4), V(0.0, -0.3, 1.0)))
    F.plant("L", 66, yaw=-24, lift=36)
    ev["hit_1"] = 60

    # ======================================================================
    # 4. figure-8 into cut 2 (f70-94): the blade loops up the left side while
    #    the left foot passes through, then a backhand diagonal
    #    (high left -> low right) that turns the body right
    # ======================================================================
    F.step("L", 71, 84, -0.20, 1.28, 8.0, h=0.12, toe_off=30)
    put(T, 77, dict(hips_x=-0.02, hips_y=0.92, hips_z=0.750, hips_yaw=34, hips_pitch=12, hips_roll=-2,
                    sp_twist=22, sp_bend=-6, sp_side=6, hd_yaw=6, hd_pitch=-4, hd_roll=0,
                    r_pole_x=0.4, r_pole_y=0.8, r_pole_z=-0.2,
                    lh_r=0.26, l_curl=0.15, l_spread=0.5, l_pole_x=-0.8, l_pole_y=-0.4, l_pole_z=-0.4),
        ldir=V(-0.55, 0.80, -0.10), lh=(V(-0.4, 0.9, 0.0), V(0.3, 0.0, 1.0)))
    put(T, 86, dict(hips_x=-0.08, hips_y=1.12, hips_z=0.630, hips_yaw=-12, hips_pitch=26, hips_roll=4,
                    sp_twist=-18, sp_bend=18, sp_side=2, hd_yaw=-4, hd_pitch=8, hd_roll=2,
                    r_pole_x=0.8, r_pole_y=-0.2, r_pole_z=-0.8,
                    lh_r=0.28, l_curl=0.05, l_spread=1.0, l_pole_x=-0.4, l_pole_y=0.2, l_pole_z=-1.0),
        ldir=V(-0.95, 0.10, -0.05), lh=(V(-1.0, 0.1, 0.0), V(0.0, 0.3, 1.0)))
    F.plant("R", 80, yaw=-20, lift=20)
    F.plant("R", 90, yaw=-46, lift=34)
    ev["hit_2"] = 85

    # ======================================================================
    # 5. spinning cut (f92-128): keeps turning right on the ball of the left
    #    foot, low and pitched forward, sword out front, the right leg
    #    stretched behind in an arabesque; the free arm starts wrapped
    #    across the chest and opens out to slow the turn
    # ======================================================================
    pivot = V(-0.20, 1.28, 0.0)
    # (frame, hips yaw, spine twist): chest yaw = hips + twist
    spin_tab = [(86, -12, -18), (92, -58, -30), (98, -112, -30), (104, -172, -26), (110, -238, -22),
                (116, -298, -16), (122, -342, -10), (128, -362, -2), (134, -368, 6)]
    yaw_s = Spline([t[0] for t in spin_tab], [float(t[1]) for t in spin_tab], (False, True))
    tw_s = Spline([t[0] for t in spin_tab], [float(t[2]) for t in spin_tab], (False, True))

    def chest(f):
        return yaw_s.at(f)[0] + tw_s.at(f)[0]
    for f, y, tw in spin_tab[1:]:
        T.key(f, "cr" if f < 128 else None, hips_yaw=y)
        T.key(f, sp_twist=tw)
    # hips orbit the pivot foot (tighter mid-spin)
    h_rel0 = rotz(V(-0.08, 1.14, 0.0) - pivot, 58)        # body frame at f92
    for f in range(92, 127, 2):
        u = (f - 92) / 34.0
        k = 1.0 - 0.6 * math.sin(math.pi * min(1.0, u * 1.2))
        h = pivot + rotz(h_rel0 * k, yaw_s.at(f)[0])
        T.key(f, "cr", hips_x=h.x, hips_y=h.y)
    for f, z, p, rl, bd, sd in ((96, 0.66, 22, 2, 12, 2), (104, 0.65, 28, 4, 16, 4), (112, 0.65, 28, 4, 16, 4),
                                (120, 0.66, 24, 2, 14, 2), (127, 0.66, 20, 0, 12, 0)):
        T.key(f, hips_z=z, hips_pitch=p, hips_roll=rl, sp_bend=bd, sp_side=sd)
    # head spots: holds on the target, whips round ahead of the body
    for f, hy in ((92, -45), (98, -90), (103, -150), (108, -260), (114, -330), (120, -360), (128, -362)):
        T.key(f, hd_yaw=hy, hd_pitch=-6, hd_roll=0)
    # free arm (keyed in the turning body frame)
    for f, d, r, curl, spr in ((94, V(0.30, 0.85, -0.05), 0.24, 0.3, 0.2), (102, V(0.45, 0.70, 0.20), 0.17, 0.5, 0.0),
                               (110, V(-0.30, 0.80, 0.35), 0.22, 0.3, 0.3), (118, V(-0.90, 0.25, 0.30), 0.28, 0.05, 0.9),
                               (125, V(-0.85, -0.45, 0.10), 0.28, 0.05, 0.9)):
        c = chest(f)
        put(T, f, dict(lh_r=r, l_curl=curl, l_spread=spr, l_pole_x=-0.5, l_pole_y=-0.6, l_pole_z=-0.5),
            ldir=rotz(d, c), lh=(rotz(V(d.x, d.y, d.z + 0.1), c), rotz(V(0.0, 0.2, 1.0), c)))
    # feet: left turns on its ball; right leg stretched out behind
    for f, yaw in ((92, -30), (98, -82), (104, -142), (110, -207), (116, -272), (122, -322), (127, -345)):
        F.plant("L", f, yaw=yaw, lift=32 if f < 125 else 18)
    r_rel = V(0.12, -0.60, 0.0)
    F.hold("R", 94)
    for f, z, lift in ((99, 0.14, 45), (104, 0.30, 50), (110, 0.36, 50), (116, 0.30, 45), (121, 0.12, 30)):
        p = pivot + rotz(r_rel, yaw_s.at(f)[0])
        F.air("R", f, p.x, p.y, z, yaw_s.at(f)[0] - 10, lift, ease="cr")
    F.plant("R", 126, 0.20, 1.40, -372, 8)
    ev["hit_3a"] = 100
    ev["hit_3b"] = 116

    # ======================================================================
    # 6. crouch + launcher (f126-150): drops deep, sword low behind, then a
    #    rising cut that takes her off the ground
    # ======================================================================
    put(T, 138, dict(hips_x=0.0, hips_y=1.36, hips_z=0.520, hips_pitch=32, hips_roll=0,
                     sp_bend=20, sp_side=0, hd_yaw=-362, hd_pitch=-12, hd_roll=0,
                     lh_r=0.28, l_curl=0.1, l_spread=0.7, l_pole_x=-0.8, l_pole_y=-0.2, l_pole_z=-0.6),
        ldir=V(-0.35, 0.55, -0.76), lh=(V(-0.2, 0.6, -0.8), V(0.4, 0.0, 0.6)))
    T.key(138, hips_yaw=-370, sp_twist=-14)
    F.plant("L", 136, yaw=-350, lift=12)
    F.plant("R", 136, lift=12)
    # push-off: heels come up, hips accelerate into the takeoff velocity
    F.plant("L", 146, lift=34)
    F.plant("R", 146, lift=34)
    put(T, 144, dict(hips_y=1.38, hips_pitch=12, sp_bend=4, hd_pitch=-14), ease="cr")
    T.key(144, "cr", hips_z=0.66)
    T.key(150, hips_z=0.90, hips_y=1.44, hips_pitch=-10, hips_yaw=-364, sp_twist=-4, sp_bend=-12)
    T.tan(150, hips_z=0.068)
    put(T, 150, dict(lh_r=0.27, l_curl=0.1, l_spread=0.6, l_pole_x=-0.8, l_pole_y=0.0, l_pole_z=0.0),
        ldir=V(-0.45, 0.20, 0.87), lh=(V(-0.3, 0.1, 1.0), V(0.0, 1.0, 0.0)))
    ev["hit_4"] = 147
    ev["jump_takeoff"] = 150

    # ======================================================================
    # 7. airborne (f150-192): rises, tucks into a front flip at the apex with
    #    the sword wheeling round her, comes out of it already pitched into
    #    a dive, sword wound up behind the head, and slams down
    # ======================================================================
    T.key(169, hips_z=1.56)
    T.tan(169, hips_z=0.0)
    T.key(179, hips_z=1.48)
    T.tan(179, hips_z=-0.022)
    T.key(189, hips_z=0.78)
    T.tan(189, hips_z=-0.092)
    T.key(195, hips_z=0.455)
    T.tan(195, hips_z=0.0)
    for f, y in ((158, 1.55), (169, 1.72), (179, 1.86), (189, 2.03), (195, 2.08)):
        T.key(f, "cr" if f < 195 else None, hips_y=y)
    T.key(169, hips_x=0.0)
    for f, p in ((156, -14), (162, 30), (166, 110), (170, 200), (174, 285), (178, 345), (182, 385),
                 (186, 400), (191, 404), (196, 402)):
        T.key(f, "cr" if f < 196 else None, hips_pitch=p)
    T.key(158, hips_yaw=-362, sp_twist=0, hips_roll=0, sp_side=0)
    for f, bd, hp in ((156, -14, -10), (162, 22, 16), (172, 30, 24), (178, 14, 6), (183, -14, -20),
                      (188, -6, -30), (193, 26, -24)):
        T.key(f, sp_bend=bd, hd_pitch=hp)
    T.key(160, hd_abs=1.0, hd_yaw=-362, hd_roll=0)
    T.key(164, hd_abs=0.0, hd_yaw=0.0)
    T.key(180, hd_abs=0.0, hd_yaw=0.0)
    T.key(186, hd_abs=1.0, hd_yaw=-362)
    # feet: hips space while airborne (tuck), back to world for the landing
    for s, x in (("L", -0.11), ("R", 0.11)):
        F.air(s, 152, x, 0.06, 0.10, -362, 30, space=1.0)
        F.air(s, 164, x, 0.24, 0.42, -362, 10, space=1.0)
        F.air(s, 176, x, 0.26, 0.46, -362, 10, space=1.0)
    # out of the tuck: legs reach down, right leg forward for the landing
    F.air("L", 182, -0.12, -0.12, 0.30, -362, 40, space=1.0)
    F.air("R", 182, 0.12, 0.22, 0.22, -362, 20, space=1.0)
    land_y = 2.08
    F.air("L", 188, -0.13, land_y - 0.36, 0.11, -350, 52, space=0.0)
    F.air("R", 188, 0.13, land_y + 0.26, 0.12, -366, 0, space=0.0)
    F.plant("L", 191, -0.13, land_y - 0.40, -350, 60)
    F.plant("R", 191, 0.13, land_y + 0.27, -366, 0)
    # left arm: swings up with the launch, hugs the knees in the tuck,
    # flies out wide and back for the dive and landing
    T.key(156, lh_space=0.0)
    T.key(162, lh_space=1.0)
    put(T, 166, dict(lh_r=0.2, l_curl=0.6, l_spread=0.0, l_pole_x=-0.6, l_pole_y=-0.4, l_pole_z=-0.4),
        ldir=V(0.15, 0.80, -0.55))
    put(T, 176, dict(lh_r=0.2), ldir=V(0.15, 0.80, -0.55))
    T.key(178, lh_space=1.0)
    T.key(184, lh_space=0.0)
    put(T, 184, dict(lh_r=0.28, l_curl=0.05, l_spread=1.0, l_pole_x=-0.6, l_pole_y=0.0, l_pole_z=-0.2),
        ldir=V(-0.80, -0.30, 0.50), lh=(V(-0.8, -0.3, 0.5), V(0.0, 0.3, 1.0)))
    put(T, 193, dict(lh_r=0.28, l_curl=0.05, l_spread=1.0, l_pole_x=-0.6, l_pole_y=0.2, l_pole_z=-0.8),
        ldir=V(-0.75, -0.60, -0.25), lh=(V(-0.7, -0.6, -0.3), V(0.0, 0.3, 1.0)))
    ev["hit_5_impact"] = 192

    # ======================================================================
    # 8. impact + moving hold (f192-214)
    # ======================================================================
    put(T, 200, dict(hips_z=0.440, hips_pitch=404, sp_bend=28, hd_pitch=-26, hips_y=2.09))
    put(T, 214, dict(hips_z=0.465, hips_pitch=398, sp_bend=24, hd_pitch=-18, hips_y=2.10,
                     lh_r=0.27, l_curl=0.2, l_spread=0.6),
        ldir=V(-0.75, -0.40, -0.45))
    for s in ("L", "R"):
        F.hold(s, 212)

    # ======================================================================
    # 9. rise into a fencer's point (f214-238): the back foot steps up and
    #    turns out, body turns side-on, blade extended at the target
    # ======================================================================
    F.step("L", 215, 230, -0.06, 2.00, -282.0, h=0.07, toe_off=30)
    F.plant("R", 226, yaw=-366, lift=0)
    put(T, 236, dict(hips_x=0.04, hips_y=2.15, hips_z=0.775, hips_pitch=372, hips_yaw=-314, hips_roll=-4,
                     sp_twist=18, sp_bend=-4, sp_side=-6, hd_yaw=-356, hd_pitch=-2, hd_roll=2,
                     r_pole_x=0.4, r_pole_y=-0.4, r_pole_z=-1.0,
                     lh_r=0.27, l_curl=0.15, l_spread=0.5, l_pole_x=-0.6, l_pole_y=-0.2, l_pole_z=-0.4),
        ldir=V(-0.30, -0.65, 0.70), lh=(V(-0.2, -0.5, 0.85), V(0.6, 0.0, 0.4)))
    put(T, 226, dict(hips_x=0.03, hips_y=2.13, hips_z=0.70, hips_pitch=382, hips_yaw=-330,
                     sp_twist=8, sp_bend=8, hd_pitch=-8), ease="cr")

    # ======================================================================
    # 10. chiburi + twirl (f238-268): the blade wheels down past the right
    #     leg and flicks out, she turns back square, then three quick turns
    #     of the sword in the hand
    # ======================================================================
    put(T, 249, dict(hips_x=0.06, hips_y=2.17, hips_z=0.74, hips_pitch=370, hips_yaw=-352, hips_roll=3,
                     sp_twist=-10, sp_bend=6, sp_side=3, hd_yaw=-360, hd_pitch=2, hd_roll=-2,
                     lh_r=0.28, l_curl=0.05, l_spread=0.9, l_pole_x=-0.3, l_pole_y=0.2, l_pole_z=-1.0),
        ldir=V(-0.90, 0.25, -0.30), lh=(V(-0.9, 0.3, -0.2), V(0.0, 0.2, 1.0)))
    F.plant("L", 240, yaw=-300, lift=8)
    F.plant("L", 250, yaw=-320, lift=0)
    put(T, 262, dict(hips_z=0.76, hips_yaw=-356, sp_twist=-6, hd_yaw=-362, lh_r=0.27, l_curl=0.3,
                     l_spread=0.3, l_pole_x=-0.5, l_pole_y=-0.5, l_pole_z=-1.0),
        ldir=V(-0.50, 0.15, -0.85), lh=IDLE_LH)
    ev["flick"] = 246
    # slopes matched at the joins (2*180/5 = 720/10 = 72 deg per frame)
    T.key(249, sw_off=0.0)
    T.key(252, sw_spin=0.0, ease="in", sw_off=0.05)
    T.key(257, sw_spin=-180.0, ease="lin")
    T.key(267, sw_spin=-900.0, ease="out")
    T.key(272, sw_spin=-1080.0, sw_off=0.05)
    T.key(276, sw_off=0.0)
    ev["twirl"] = 252

    # ======================================================================
    # 11. dismiss (f272-300): the blade hangs low behind her right hip and
    #     breaks up tip -> hilt while she glances down at it; then she
    #     steps into idle on the new spot
    # ======================================================================
    put(T, 282, dict(hips_z=0.78, hips_yaw=-362, sp_twist=-8, hips_roll=3, sp_side=2,
                     r_curl=1.0, r_pole_x=0.6, r_pole_y=-0.3, r_pole_z=-1.0))
    T.key(276, hd_yaw=-362, hd_pitch=0, hd_roll=-2)
    T.key(286, hd_yaw=-402, hd_pitch=20, hd_roll=-8)
    T.key(298, hd_yaw=-398, hd_pitch=16, hd_roll=-6)
    ev["dismiss_start"] = 280
    T.key(280, sw_mat=1.0)
    T.key(300, sw_mat=0.0, ease="inout")
    put(T, 302, dict(r_curl=0.25, rh_r=0.29), ease="out")
    ox, oy = 0.06, 2.20
    F.step("R", 294, 308, IDLE_FEET["R"][0] + ox, IDLE_FEET["R"][1] + oy, IDLE_FEET["R"][2] - 360, h=0.04)
    F.step("L", 304, 318, IDLE_FEET["L"][0] + ox, IDLE_FEET["L"][1] + oy, IDLE_FEET["L"][2] - 360, h=0.04)
    put(T, 308, dict(hips_x=0.07, hips_y=2.20, hips_z=0.80, hips_pitch=364, hips_yaw=-370, hips_roll=-1,
                     sp_twist=2, sp_bend=3, sp_side=1, hd_yaw=-364, hd_pitch=4, hd_roll=-2))
    idle_pose(326, ox, oy, feet=False)
    idle_pose(344, ox, oy, feet=False)
    for s in ("L", "R"):
        F.hold(s, 344)
    ev["end"] = 344

    # ======================================================================
    # sword paths
    # ======================================================================
    # draw -> loop -> cut 1 -> loop -> cut 2 -> spin -> low guard behind
    keys = [
        (27, V(-0.35, -1.0, -0.25), V(-0.75, 0.20, -0.62), 0.25),
        (32, V(-0.80, 0.50, -0.30), V(-0.50, 0.70, -0.50), 0.27),
        (35, V(-0.05, 1.0, -0.08), V(0.0, 0.95, -0.30), 0.30),
        (38, V(0.80, 0.60, 0.0), V(0.68, 0.70, -0.20), 0.315),
        (42, V(0.96, -0.30, 0.08), V(0.95, 0.25, -0.12), 0.31),
        # loop up behind the right shoulder
        (47, V(0.45, -0.80, 0.42), V(0.80, -0.05, 0.40), 0.27),
        (52, V(-0.10, -0.55, 0.83), V(0.45, 0.15, 0.85), 0.25, 30),
        # cut 1: forehand diagonal down
        (56, V(0.30, 0.40, 0.87), V(0.45, 0.50, 0.72), 0.29),
        (59, V(0.25, 0.95, 0.20), V(0.25, 0.92, 0.25), 0.315),
        (62, V(-0.45, 0.62, -0.65), V(-0.10, 0.90, -0.40), 0.315),
        (67, V(-0.80, -0.32, -0.40), V(-0.55, 0.50, -0.55), 0.29),
        # loop up the left side and wrap behind the head
        (72, V(-0.55, -0.80, 0.22), V(-0.45, 0.40, 0.45), 0.26),
        (76, V(0.05, -0.95, 0.30), V(-0.30, 0.25, 0.92), 0.27),
        (80, V(-0.25, 0.05, 0.97), V(-0.25, 0.45, 0.86), 0.28, -15),
        # cut 2: backhand diagonal down
        (83, V(-0.12, 0.85, 0.50), V(-0.05, 0.75, 0.60), 0.30),
        (85, V(0.10, 1.0, 0.0), V(0.15, 0.95, 0.10), 0.315),
        (88, V(0.62, 0.50, -0.60), V(0.55, 0.75, -0.30), 0.315),
    ]
    # spin: sword out in front of the turning chest, blade a little low
    for f in range(92, 125, 4):
        c = chest(f)
        if f == 92:
            b, g = V(0.85, 0.35, -0.35), V(0.85, 0.35, -0.40)
        else:
            b, g = V(0.60, 0.78, -0.20), V(0.70, 0.62, -0.32)
        keys.append((f, rotz(b, c), rotz(g, c), 0.31 if f == 92 else 0.315))
    keys += [
        (130, rotz(V(0.75, -0.30, -0.45), -366), rotz(V(0.75, 0.10, -0.62), -366), 0.30),
        (138, rotz(V(0.55, -0.75, -0.36), -370), rotz(V(0.62, -0.20, -0.76), -370), 0.29),
    ]
    blade_path(T, keys)
    # launcher: low behind -> forward -> overhead (takeoff at f150)
    blade_path(T, [
        (138, rotz(V(0.55, -0.75, -0.36), -370), rotz(V(0.62, -0.20, -0.76), -370), 0.29),
        (142, V(0.30, 0.76, -0.52), V(0.30, 0.50, -0.80), 0.30),
        (145, V(0.15, 1.0, 0.0), V(0.12, 0.85, -0.30), 0.315),
        (148, V(0.05, 0.55, 0.84), V(0.10, 0.50, 0.70), 0.31),
        (152, V(0.0, -0.30, 0.95), V(0.10, 0.10, 0.99), 0.29),
    ], ends=(False, True))
    # flip: chest space, sword overhead with the blade down the back
    T.key(155, rh_space=0.0)
    T.key(161, rh_space=1.0)
    flip_sw = (V(0.05, -0.75, 0.66), V(0.0, -0.66, -0.75))
    for f in (161, 170, 176):
        put(T, f, dict(rh_r=0.25, r_pole_x=0.8, r_pole_y=0.0, r_pole_z=0.1),
            rdir=V(0.15, 0.25, 0.96), sw=flip_sw)
    T.key(176, rh_space=1.0)
    T.key(181, rh_space=0.0)
    # the blade keeps wheeling forward out of the flip: over the top and
    # straight down into the ground
    blade_path(T, [
        (181, V(0.05, -0.75, 0.66), V(0.12, 0.05, 0.99), 0.25),
        (185, V(0.05, -0.15, 0.99), V(0.08, 0.25, 0.97), 0.27),
        (188, V(0.08, 0.70, 0.71), V(0.10, 0.70, 0.70), 0.30),
        (190, V(0.14, 1.0, -0.05), V(0.18, 0.92, 0.25), 0.315),
        (192, V(0.24, 0.80, -0.55), V(0.28, 0.88, -0.38), 0.315),
        (197, V(0.36, 0.79, -0.50), V(0.38, 0.76, -0.52), 0.30),
    ], ends=(False, True), edge0=V(0.0, 1.0, 0.0))
    put(T, 212, dict(rh_r=0.30, r_pole_x=0.7, r_pole_y=-0.4, r_pole_z=-0.6),
        rdir=V(0.40, 0.76, -0.50), sw=(V(0.36, 0.79, -0.50), V(0.0, -0.70, -0.70)))
    # rise into the point -> chiburi wheel down past the right leg -> flick
    blade_path(T, [
        (214, V(0.36, 0.79, -0.50), V(0.40, 0.76, -0.50), 0.30),
        (226, V(0.15, 0.95, -0.25), V(0.20, 0.90, -0.30), 0.30),
        (236, V(0.15, 0.98, -0.12), V(0.12, 0.98, -0.12), 0.315),
        (241, V(0.30, 0.55, 0.78), V(0.40, 0.70, 0.30), 0.30),
        (244, V(0.45, -0.40, 0.80), V(0.65, 0.20, 0.20), 0.28),
        (247, V(0.55, -0.55, -0.62), V(0.80, -0.10, -0.40), 0.30),
        (252, V(0.40, 0.85, -0.35), V(0.75, 0.40, -0.45), 0.30),
    ], ends=(True, True), edge0=V(0.0, 0.0, 1.0))
    # twirl beside the leg, then let the blade hang low behind the hip
    put(T, 260, dict(rh_r=0.30), rdir=V(0.86, 0.36, -0.36), sw=(V(0.32, 0.95, 0.02), V(0.0, 0.2, -1.0)))
    put(T, 268, dict(rh_r=0.30), rdir=V(0.86, 0.36, -0.37), sw=(V(0.30, 0.95, 0.0), V(0.0, 0.2, -1.0)))
    put(T, 282, dict(rh_r=0.31), rdir=V(0.80, -0.15, -0.58), sw=(V(0.55, -0.60, -0.58), V(0.0, -0.60, 0.80)))
    put(T, 296, dict(rh_r=0.31), rdir=V(0.78, -0.12, -0.61), sw=(V(0.55, -0.58, -0.60), V(0.0, -0.60, 0.80)))

    T.events = ev
    T.end = 344
    T.bake_cache()
    if rig is not None:
        rig.fit_sword_grip(T)
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
