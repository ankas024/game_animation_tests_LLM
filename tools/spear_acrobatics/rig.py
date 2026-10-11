"""Pose solver for the ch_02 Mixamo rig plus a bendable spear.

World conventions (Blender world, metres): +Z up. The character's rest pose
faces -Y. The comparison cameras sit on the -Y side looking along +Y, so +X
is screen right and "yaw 0" means facing the camera.

A pose is a flat dict of scalar channels (see DEFAULTS). Rig.solve() turns it
into a world rotation + head position for every bone, Rig.apply() writes
those to the armature as pose-bone matrix_basis values.

Channel groups
  hips      hx hy hz (pelvis head, m), yaw pitch roll twist (deg)
            yaw + turns left, pitch + leans forward (front flip),
            roll + leans to her right (cartwheel), twist about the body axis
  spine     sb (bend fwd) ss (side, + to her right) st (twist, + left)
  head      nb ns nt, relative to the chest
  legs      prefix ll_ / rl_
            w: 0 = FK, 1 = IK (ball of the foot pinned in world space)
            FK: fl (hip flexion, + thigh forward) ab (abduction) ex (knee out)
                kn (knee bend) an (ankle, + toes down)
            IK: bx by bz (ball of foot), yaw (foot facing, same as hips yaw),
                pit (+ heel up), rol, ko (knee swivel out)
  arms      prefix la_ / ra_
            FK: az (0 fwd, + out to the side) el (+ up) d (reach, 0..1 of arm)
                sw (elbow swivel) wf wd wt (wrist flex / deviation / twist)
                curl (fingers when free) shu shf (clavicle up / forward)
            spear: h (0 free .. 1 hand closed on the shaft)
                   s (grip position on the shaft, m from the centre, + toward
                   the blade), g (+1 thumb toward the blade, -1 toward the
                   butt), gr (grip roll about the shaft)
  spear     sang (angle in the camera plane, 0 = screen right, 90 = up)
            sdep (tilt into the screen), sroll, sk (curvature 1/m), skd
            (bend direction around the shaft), anchor: sx sy sz = world
            position of the shaft point at arclength sa;
            sat 1: sang/sdep are the shaft direction at the anchor, not the centre
            scr / scl: carried by the right / left hand (anchor = that hand's
            FK grip, the hand leads and the spear follows)
"""
import math

from mathutils import Matrix, Vector

P = "mixamorig:"
SPEAR = "weapon_spear"
SPEAR_LEN = 2.0
SPEAR_SEG = 3                    # bones per half of the shaft
SEG = SPEAR_LEN / (2 * SPEAR_SEG)
SPEAR_FWD = [SPEAR] + [f"weapon_spear_f{i}" for i in range(1, SPEAR_SEG)]
SPEAR_BACK = [f"weapon_spear_b{i}" for i in range(SPEAR_SEG)]

R0 = Vector((-1.0, 0.0, 0.0))    # character right at rest
F0 = Vector((0.0, -1.0, 0.0))    # character forward at rest
U0 = Vector((0.0, 0.0, 1.0))

FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
GRIP_TILT = 18.0                 # shaft leans toward the fingers on the thumb side
GRIP_OFF = (0.0, 0.056, 0.024)   # fist centre in (thumb, fingers, palm) axes, m


def rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 3, Vector(axis))


def body_rot(yaw=0.0, pitch=0.0, roll=0.0, twist=0.0):
    return rot(U0, yaw) @ rot(R0, -pitch) @ rot(F0, roll) @ rot(U0, twist)


def basis(x, y):
    """Rotation with exact Y axis y and X axis as close as possible to x."""
    y = y.normalized()
    x = (x - x.dot(y) * y)
    if x.length < 1e-8:
        x = y.orthogonal()
    x.normalize()
    z = x.cross(y)
    return Matrix((x, y, z)).transposed()


def clamp(v, a, b):
    return max(a, min(b, v))


def slerp_m(a, b, t):
    t = clamp(t, 0.0, 1.0)
    if t <= 0.0:
        return a.copy()
    if t >= 1.0:
        return b.copy()
    return a.to_quaternion().slerp(b.to_quaternion(), t).to_matrix()


def spear_dir(ang, dep):
    a, d = math.radians(ang), math.radians(dep)
    return Vector((math.cos(d) * math.cos(a), math.sin(d), math.cos(d) * math.sin(a)))


DEFAULTS = dict(
    hx=0.0, hy=-0.024, hz=0.848, yaw=0.0, pitch=0.0, roll=0.0, twist=0.0,
    sb=0.0, ss=0.0, st=0.0, nb=0.0, ns=0.0, nt=0.0,
    sang=90.0, sdep=0.0, sroll=0.0, sk=0.0, skd=0.0, skp=0.0,
    sx=-0.5, sy=0.0, sz=0.9, sa=0.0, sat=0.0, scr=0.0, scl=0.0,
)
for _s, _x in (("l", 1.0), ("r", -1.0)):
    DEFAULTS.update({
        _s + "l_w": 0.0, _s + "l_fl": 0.0, _s + "l_ab": 3.0, _s + "l_ex": 0.0,
        _s + "l_kn": 0.0, _s + "l_an": 0.0,
        _s + "l_bx": 0.108 * _x, _s + "l_by": -0.055, _s + "l_bz": 0.0,
        _s + "l_yaw": 0.0, _s + "l_pit": 0.0, _s + "l_rol": 0.0, _s + "l_ko": 0.0,
        _s + "a_az": 80.0, _s + "a_el": -75.0, _s + "a_d": 0.95, _s + "a_sw": 0.0,
        _s + "a_wf": 0.0, _s + "a_wd": 0.0, _s + "a_wt": 0.0, _s + "a_curl": 0.35,
        _s + "a_shu": 0.0, _s + "a_shf": 0.0,
        _s + "a_h": 0.0, _s + "a_s": 0.0, _s + "a_g": 1.0, _s + "a_gr": 0.0,
    })


class Rig:
    def __init__(self, arm):
        self.arm = arm
        mw = arm.matrix_world
        self.obj_rot = mw.to_3x3().normalized()
        self.obj_scale = mw.to_scale()[0]
        self.q, self.h, self.tail = {}, {}, {}
        for b in arm.data.bones:
            loc, r, _ = (mw @ b.matrix_local).decompose()
            self.q[b.name] = r.to_matrix()
            self.h[b.name] = loc
            self.tail[b.name] = mw @ b.tail_local
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        self.order = [b.name for b in arm.data.bones]
        h = self.h
        self.len = {}
        for s in ("Left", "Right"):
            self.len[s + "Arm"] = (h[P + s + "ForeArm"] - h[P + s + "Arm"]).length
            self.len[s + "Fore"] = (h[P + s + "Hand"] - h[P + s + "ForeArm"]).length
            self.len[s + "Thigh"] = (h[P + s + "Leg"] - h[P + s + "UpLeg"]).length
            self.len[s + "Shin"] = (h[P + s + "Foot"] - h[P + s + "Leg"]).length
        back = Vector((0, 1, 0))
        self.hinge0 = {
            "RightArm": back.cross(Vector((-1, 0, 0))),
            "LeftArm": back.cross(Vector((1, 0, 0))),
            "LeftUpLeg": F0.cross(Vector((0, 0, -1))),
            "RightUpLeg": F0.cross(Vector((0, 0, -1))),
        }
        self.ankle_from_ball = {s: h[P + s + "Foot"] - h[P + s + "ToeBase"] for s in ("Left", "Right")}
        # hand frames: columns (thumb, fingers, palm normal) at rest
        self.hand_rest = {}
        for s in ("Left", "Right"):
            q = self.q[P + s + "Hand"]
            fing = (q @ Vector((0, 1, 0))).normalized()
            th = h[P + s + "HandThumb1"] - h[P + s + "Hand"]
            th = (th - th.dot(fing) * fing).normalized()
            palm = th.cross(fing) if s == "Right" else fing.cross(th)
            self.hand_rest[s] = Matrix((th, fing, palm)).transposed()
        self.curl_axis = {}
        for s in ("Left", "Right"):
            palm = self.hand_rest[s].col[2]
            for f in FINGERS:
                for i in (1, 2, 3):
                    n = P + f"{s}Hand{f}{i}"
                    d = (self.tail[n] - h[n]).normalized()
                    self.curl_axis[n] = d.cross(palm).normalized()
        self.spear_ok = SPEAR in arm.data.bones
        self.half = SPEAR_LEN / 2
        self._clav_sj, self._miss = {}, {}

    # ------------------------------------------------------------------ IK
    @staticmethod
    def two_bone(S, T, pole, l1, l2, soft=0.0):
        d = T - S
        dist = d.length
        a = d / max(dist, 1e-9)
        L = l1 + l2
        if soft > 0.0:
            ds = L * (1.0 - soft)
            if dist > ds:
                dist = ds + (L - ds) * (1.0 - math.exp(-(dist - ds) / (L - ds)))
        dist = clamp(dist, abs(l1 - l2) + 1e-4, L * 0.9999)
        cos_a = clamp((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1)
        al = math.acos(cos_a)
        p = pole - pole.dot(a) * a
        if p.length < 1e-6:
            p = a.orthogonal()
        p.normalize()
        E = S + a * (l1 * math.cos(al)) + p * (l1 * math.sin(al))
        n = p.cross(a).normalized()
        return E, n, S + a * dist

    def limb_rot(self, bone, direction, hinge, hinge0):
        q = self.q[bone]
        d0 = q @ Vector((0, 1, 0))
        return basis(hinge, direction) @ basis(hinge0, d0).transposed() @ q

    # ------------------------------------------------------------ spear
    def spear_frame(self, c):
        """Centre frame (columns X, Y=shaft toward blade, Z) and bend data."""
        d = spear_dir(c["sang"], c["sdep"])
        ref = U0.cross(d)
        if ref.length < 0.15:
            ref = Vector((0, 1, 0)).cross(d) * (0.15 - ref.length) / 0.15 + ref
        Fm = basis(ref, d)
        Fm = rot(d, c["sroll"]) @ Fm
        k = c["sk"]
        # bend: both ends curve toward direction (skd in the camera plane,
        # 0 = screen right, 90 = up; skp tilts it into the screen)
        a, p = math.radians(c["skd"]), math.radians(c["skp"])
        B = Vector((math.cos(a) * math.cos(p), math.sin(p), math.sin(a) * math.cos(p)))
        nb = B - B.dot(d) * d
        if nb.length < 1e-4:
            nb = Fm.col[0]
        nb.normalize()
        if c["sat"] > 0.5 and abs(k) > 1e-6:
            # sang/sdep give the tangent at the anchor point: rotate back to the centre
            ax = Fm.col[1].cross(nb)
            if ax.length > 1e-9:
                R = rot(ax.normalized(), -math.degrees(k * c["sa"]))
                Fm, nb = R @ Fm, R @ nb
        return Fm, k, nb

    @staticmethod
    def arc(Fm, k, nb, s):
        """Offset from the centre and tangent at arclength s."""
        y = Fm.col[1]
        if abs(k) < 1e-6:
            return y * s, y.copy()
        off = y * (math.sin(k * s) / k) + nb * ((1 - math.cos(k * s)) / k)
        t = y * math.cos(k * s) + nb * math.sin(k * s)
        return off, t.normalized()

    def arc_rot(self, Fm, k, nb, s):
        ax = Fm.col[1].cross(nb)
        if abs(k) < 1e-6 or ax.length < 1e-9:
            return Fm.copy()
        return rot(ax.normalized(), math.degrees(k * s)) @ Fm

    # ------------------------------------------------------------ hands
    def grip_frame(self, s, shaft, g, p, groll):
        """Hand rotation closing the fist around a shaft with direction `shaft`
        (thumb side toward g*shaft). p ~ forearm direction."""
        a = shaft * g
        F0v = p - p.dot(a) * a
        if F0v.length < 1e-4:
            F0v = a.orthogonal()
        F0v.normalize()
        F0v = rot(a, groll) @ F0v
        tau = math.radians(GRIP_TILT)
        T = a * math.cos(tau) - F0v * math.sin(tau)
        Fv = F0v * math.cos(tau) + a * math.sin(tau)
        N = T.cross(Fv) if s == "Right" else Fv.cross(T)
        B = Matrix((T, Fv, N)).transposed()
        return B @ self.hand_rest[s].transposed() @ self.q[P + s + "Hand"]

    def grip_offset(self, s, R_hand):
        B = R_hand @ self.q[P + s + "Hand"].transposed() @ self.hand_rest[s]
        return B @ Vector(GRIP_OFF)

    # ------------------------------------------------------------ solve
    def solve(self, pose):
        c = dict(DEFAULTS)
        c.update(pose)
        R, H, G = {}, {}, {}

        def place(name, g, head=None):
            G[name] = g
            R[name] = g @ self.q[name]
            if head is None:
                par = self.parent[name]
                head = H[par] + G[par] @ (self.h[name] - self.h[par])
            H[name] = head

        def place_rot(name, r, head=None):
            place(name, r @ self.q[name].transposed(), head)

        Gh = body_rot(c["yaw"], c["pitch"], c["roll"], c["twist"])
        place(P + "Hips", Gh, Vector((c["hx"], c["hy"], c["hz"])))
        g = Gh
        for nm, f in (("Spine", 0.30), ("Spine1", 0.33), ("Spine2", 0.37)):
            g = g @ body_rot(c["st"] * f, c["sb"] * f, c["ss"] * f)
            place(P + nm, g)
        Gc = g
        place(P + "Neck", Gc @ body_rot(c["nt"] * 0.4, c["nb"] * 0.4, c["ns"] * 0.4))
        place(P + "Head", Gc @ body_rot(c["nt"], c["nb"], c["ns"]))
        for nm in ("HeadTop_End", "HeadTop_End_end"):
            if P + nm in self.q:
                place(P + nm, G[self.parent[P + nm]])

        for s, k in (("Left", "ll_"), ("Right", "rl_")):
            self._leg(c, s, k, Gh, place, place_rot, H, G)

        # ---- arms, phase 1: clavicles + FK arms (needed for carried spears)
        Fm, kk, nb = self.spear_frame(c)
        ph1 = {}
        for s, k in (("Left", "la_"), ("Right", "ra_")):
            Sj = self._clav(c, s, k, Gc, c[k + "el"], place, H)
            dirv = self._fk_dir(c, k, s, Gc)
            ph1[s] = (Sj, dirv) + self._arm_ik(c, s, k, Gc, Sj, Sj + dirv * self._reach(c, k, s))

        # ---- spear anchor (world, or carried by a hand)
        cr, cl = clamp(c["scr"], 0, 1), clamp(c["scl"], 0, 1)
        sa = c["sa"] * (1 - cr - cl) + c["ra_s"] * cr + c["la_s"] * cl
        anchor = Vector((c["sx"], c["sy"], c["sz"])) * (1 - cr - cl)
        for s, w, k in (("Right", cr, "ra_"), ("Left", cl, "la_")):
            if w <= 0.0:
                continue
            Sj, dirv, E, n, Weff, pf = ph1[s]
            _, tan_s = self.arc(Fm, kk, nb, c[k + "s"])
            Rg = self.grip_frame(s, tan_s, c[k + "g"], pf, c[k + "gr"])
            anchor += (Weff + self.grip_offset(s, Rg)) * w
        off_a, _ = self.arc(Fm, kk, nb, sa)
        self.spear_state = (anchor - off_a, Fm, kk, nb)

        # ---- arms, phase 2 (a world-placed spear is nudged toward hands that
        # cannot reach it, then the arms are solved again)
        self._clav_sj = {s: ph1[s][0] for s in ph1}
        self._miss = {}
        for it in range(2):
            for s, k in (("Left", "la_"), ("Right", "ra_")):
                self._arm(c, s, k, Gc, ph1[s], place, place_rot, H, G)
            free_w = clamp(1.0 - cr - cl, 0.0, 1.0)
            ms = [(m, w) for m, w in self._miss.values() if w > 0]
            if it or free_w <= 0 or not ms:
                break
            shift = sum((m for m, w in ms), Vector()) * (1.0 / len(ms))
            if shift.length < 0.01:
                break
            centre, Fm, kk, nb = self.spear_state
            self.spear_state = (centre - shift * free_w, Fm, kk, nb)

        for nm in self.order:
            if nm not in G and not nm.startswith("weapon_"):
                place(nm, G[self.parent[nm]])

        if self.spear_ok:
            self._spear_bones(place, H, G)
        return R, H, G

    def _spear_bones(self, place, H, G):
        centre, Fm, k, nb = self.spear_state
        flip = rot((1, 0, 0), 180.0)
        for sign, names in ((1.0, SPEAR_FWD), (-1.0, SPEAR_BACK)):
            for i, n in enumerate(names):
                s0, s1 = sign * SEG * i, sign * SEG * (i + 1)
                off0, _ = self.arc(Fm, k, nb, s0)
                Rm = self.arc_rot(Fm, k, nb, 0.5 * (s0 + s1))
                if sign < 0:
                    Rm = Rm @ flip              # bone +Y runs toward the butt
                place(n, Rm @ self.q[n].transposed(), centre + off0)

    # ------------------------------------------------------------------ legs
    def _leg(self, c, s, k, Gh, place, place_rot, H, G):
        side = 1.0 if s == "Left" else -1.0
        w = clamp(c[k + "w"], 0.0, 1.0)
        Hj = H[P + "Hips"] + Gh @ (self.h[P + s + "UpLeg"] - self.h[P + "Hips"])
        l1, l2 = self.len[s + "Thigh"], self.len[s + "Shin"]
        # FK chain
        Dth = rot(R0, c[k + "fl"]) @ rot(F0, side * c[k + "ab"]) @ rot(U0, side * c[k + "ex"])
        Gth = Gh @ Dth
        Gsh = Gth @ rot(R0, -c[k + "kn"])
        Gft = Gsh @ rot(R0, -c[k + "an"])
        knee_fk = Hj + Gth @ (self.h[P + s + "Leg"] - self.h[P + s + "UpLeg"])
        ankle_fk = knee_fk + Gsh @ (self.h[P + s + "Foot"] - self.h[P + s + "Leg"])
        # IK target
        Rf = body_rot(c[k + "yaw"]) @ rot(R0, -c[k + "pit"]) @ rot(F0, c[k + "rol"])
        ball = Vector((c[k + "bx"], c[k + "by"], c[k + "bz"]))
        ankle_ik = ball + Rf @ self.ankle_from_ball[s]
        ankle = ankle_fk.lerp(ankle_ik, w)
        Rfoot = slerp_m(Gft, Rf, w)
        # knee pole
        mid = (Hj + ankle_fk) * 0.5
        pole_fk = knee_fk - mid
        if pole_fk.length < 1e-4:
            pole_fk = Gth @ F0
        fwd = Rf @ F0
        hips_fwd = Gh @ F0
        pole_ik = fwd * 0.6 + hips_fwd * 0.4
        pole_ik = rot(Rf @ U0, side * (8.0 + c[k + "ko"])) @ pole_ik
        pole = pole_fk.normalized().lerp(pole_ik.normalized(), w)
        E, n, _ = self.two_bone(Hj, ankle, pole, l1, l2, soft=0.02 * w)
        place_rot(P + s + "UpLeg", self.limb_rot(P + s + "UpLeg", (E - Hj).normalized(), n,
                                                 self.hinge0[s + "UpLeg"]), Hj)
        sd = (ankle - E).normalized()
        place_rot(P + s + "Leg", self.limb_rot(P + s + "Leg", sd, n, self.hinge0[s + "UpLeg"]), E)
        place(P + s + "Foot", Rfoot, E + sd * l2)
        # toes stay flat on the floor while the ball is planted and the heel is up
        flat = clamp(1.0 - c[k + "bz"] / 0.04, 0.0, 1.0) * w
        g_toe = slerp_m(Rfoot, body_rot(c[k + "yaw"]) @ rot(F0, c[k + "rol"]), flat)
        place(P + s + "ToeBase", g_toe)
        for nm in (s + "Toe_End", s + "Toe_End_end"):
            if P + nm in self.q:
                place(P + nm, G[self.parent[P + nm]])

    # ------------------------------------------------------------------ arms
    def _clav(self, c, s, k, Gc, el, place, H):
        side = 1.0 if s == "Left" else -1.0
        auto = clamp((el + 10.0) / 100.0, 0.0, 1.0) * 18.0
        g_sh = Gc @ rot(F0, side * (c[k + "shu"] + auto)) @ rot(U0, -side * c[k + "shf"])
        place(P + s + "Shoulder", g_sh)
        return H[P + s + "Shoulder"] + g_sh @ (self.h[P + s + "Arm"] - self.h[P + s + "Shoulder"])

    def _fk_dir(self, c, k, s, Gc):
        side = 1.0 if s == "Left" else -1.0
        el = math.radians(c[k + "el"])
        hd = rot(U0, side * c[k + "az"]) @ F0
        return (Gc @ (hd * math.cos(el) + U0 * math.sin(el))).normalized()

    def _reach(self, c, k, s):
        return clamp(c[k + "d"], 0.15, 1.0) * (self.len[s + "Arm"] + self.len[s + "Fore"])

    def _pole(self, c, s, k, Gc, Sj, W):
        side = 1.0 if s == "Left" else -1.0
        out = -R0 if s == "Left" else R0
        pole = Gc @ (Vector((0, 1, 0)) * 0.6 + Vector((0, 0, -1)) * 1.0 + out * 0.4)
        axis = (W - Sj)
        if axis.length > 1e-6:
            pole = rot(axis.normalized(), -side * c[k + "sw"]) @ pole
        return pole

    def _arm_ik(self, c, s, k, Gc, Sj, W, pole=None):
        l1, l2 = self.len[s + "Arm"], self.len[s + "Fore"]
        if pole is None:
            pole = self._pole(c, s, k, Gc, Sj, W)
        E, n, Weff = self.two_bone(Sj, W, pole, l1, l2, soft=0.03)
        return E, n, Weff, (Weff - E).normalized()

    def _grip_solve(self, c, s, k, Gc, dirv, pf, att, sv, place, H):
        """IK an arm onto the shaft at arclength sv. Returns the solution and
        the miss vector (grip point - fist centre)."""
        l2 = self.len[s + "Fore"]
        centre, Fm, kk, nb = self.spear_state
        off_s, tan_s = self.arc(Fm, kk, nb, sv)
        grip_pt = centre + off_s
        Sj = self._clav_sj.get(s)
        v = Gc.transposed() @ (grip_pt - Sj)
        el_g = math.degrees(math.asin(clamp(v.normalized().z, -1, 1))) if v.length > 1e-6 else 0
        el_use = c[k + "el"] * (1 - att) + el_g * att
        Sj = self._clav(c, s, k, Gc, el_use, place, H)
        Wfk = Sj + dirv * self._reach(c, k, s)
        p = (grip_pt - Sj).normalized().lerp(pf, 1 - att).normalized()
        for _ in range(3):
            R_grip = self.grip_frame(s, tan_s, c[k + "g"], p, c[k + "gr"])
            W = Wfk.lerp(grip_pt - self.grip_offset(s, R_grip), att)
            pole = self._pole(c, s, k, Gc, Sj, W)
            pole = pole.normalized().lerp((W - p * l2 - Sj).normalized(), 0.35 * att)
            E, n, Weff, p_new = self._arm_ik(c, s, k, Gc, Sj, W, pole)
            done = (p_new - p).length < 1e-3
            p = p_new
            if done:
                break
        fist = Weff + self.grip_offset(s, R_grip)
        return Sj, E, n, Weff, R_grip, tan_s, el_use, (grip_pt - fist) * att

    def _arm(self, c, s, k, Gc, ph1, place, place_rot, H, G):
        side = 1.0 if s == "Left" else -1.0
        hold = clamp(c[k + "h"], 0.0, 1.0)
        carry = clamp(c["scr"] if s == "Right" else c["scl"], 0.0, 1.0)
        att = hold * (1.0 - carry)
        Sj0, dirv, E, n, Weff, pf = ph1
        Sj = Sj0
        centre, Fm, kk, nb = self.spear_state
        sv = c[k + "s"]
        off_s, tan_s = self.arc(Fm, kk, nb, sv)
        R_grip = None
        self._miss[s] = (Vector(), 0.0)
        if att > 0.0:
            best = None
            for _ in range(2):
                res = self._grip_solve(c, s, k, Gc, dirv, pf, att, sv, place, H)
                if best is None or res[-1].length < best[-1].length:
                    best = res
                miss = res[-1]
                if miss.length < 0.015:
                    break
                # out of reach: slide the grip along the shaft toward the shoulder
                gp = centre + self.arc(Fm, kk, nb, sv)[0]
                t = self.arc(Fm, kk, nb, sv)[1]
                ds = clamp((res[0] - gp).dot(t), -0.4, 0.4)
                sv = clamp(sv + ds, -self.half + 0.06, self.half - 0.06)
            Sj, E, n, Weff, R_grip, tan_s, el_use, miss = best
            self._clav(c, s, k, Gc, el_use, place, H)   # clavicle of the attempt kept
            self._miss[s] = (miss, att)
        elif hold > 0.0:
            R_grip = self.grip_frame(s, tan_s, c[k + "g"], pf, c[k + "gr"])
        r_up = self.limb_rot(P + s + "Arm", (E - Sj).normalized(), n, self.hinge0[s + "Arm"])
        place_rot(P + s + "Arm", r_up, Sj)
        fd = (Weff - E).normalized()
        r_fore = self.limb_rot(P + s + "ForeArm", fd, n, self.hinge0[s + "Arm"])
        qf, qh = self.q[P + s + "ForeArm"], self.q[P + s + "Hand"]
        B = self.hand_rest[s]
        Gf = r_fore @ qf.transposed()
        R_free = Gf @ rot(B.col[1], side * c[k + "wt"]) @ rot(B.col[0], c[k + "wf"]) \
            @ rot(B.col[2], c[k + "wd"]) @ qh
        R_hand = slerp_m(R_free, R_grip, hold) if R_grip is not None else R_free
        # push ~60% of the hand roll about the forearm axis into the forearm bone
        D = Gf.transposed() @ (R_hand @ qh.transposed())
        tw = (qf.transposed() @ D @ qf).to_quaternion().to_swing_twist('Y')[1]
        r_fore = r_fore @ Matrix.Rotation(tw * 0.6, 3, 'Y')
        place_rot(P + s + "ForeArm", r_fore, E)
        place_rot(P + s + "Hand", R_hand, Weff)
        curl = c[k + "curl"] * (1 - hold) + 0.85 * hold
        self._fingers(s, curl, G, place)

    def _fingers(self, s, curl, G, place):
        gh = G[P + s + "Hand"]
        fist = {1: 70.0, 2: 95.0, 3: 55.0}
        for f in FINGERS:
            g = gh
            for i in (1, 2, 3):
                n = P + f"{s}Hand{f}{i}"
                if n not in self.q:
                    continue
                if f == "Thumb":
                    ang = {1: 15.0, 2: 25.0, 3: 35.0}[i] * curl
                else:
                    ang = fist[i] * curl
                g = g @ rot(self.curl_axis[n], ang)
                place(n, g)
            for n in (P + f"{s}Hand{f}4", P + f"{s}Hand{f}4_end"):
                if n in self.q:
                    place(n, G[self.parent[n]])

    # ------------------------------------------------------------------ apply
    def apply(self, pose):
        R, H, G = self.solve(pose)
        inv = self.obj_rot.transposed()
        sc = self.obj_scale
        A = {}
        for n in self.order:
            M = (inv @ R[n]).to_4x4()
            M.translation = inv @ H[n] / sc
            A[n] = M
        bones = self.arm.data.bones
        for n in self.order:
            b = bones[n]
            par = self.parent[n]
            if par is None:
                m = b.matrix_local.inverted() @ A[n]
            else:
                rest_rel = bones[par].matrix_local.inverted() @ b.matrix_local
                m = rest_rel.inverted() @ A[par].inverted() @ A[n]
            self.arm.pose.bones[n].matrix_basis = m
        return R, H
