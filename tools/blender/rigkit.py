"""
rigkit - a small procedural pose solver for the ch_02 Mixamo rig.

Everything is authored in *character space*:
    +x = character's right, +y = character's forward, +z = up, metres,
    origin on the ground under the rest-pose hips.

A pose is a flat dict of scalar channels (see DEFAULTS).  `Rig.solve()`
turns a pose into per-bone rotations/positions (FK spine, analytic two-bone
IK for arms and legs, ball-pivot feet, finger curls, a weapon bone) and
`Rig.apply()` writes them to the armature as pose-bone matrix_basis values,
ready to be keyed / exported.
"""
import math
import bpy
from mathutils import Matrix, Vector, Quaternion

P = "mixamorig:"
WEAPON = "weapon_r"

# K maps character space -> Blender world at rest (character faces -Y).
K = Matrix(((-1, 0, 0), (0, -1, 0), (0, 0, 1)))

FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")


# --------------------------------------------------------------------------
# small math helpers
# --------------------------------------------------------------------------
def rad(d):
    return math.radians(d)


def axis_rot(axis, deg):
    return Matrix.Rotation(rad(deg), 3, Vector(axis))


def ypr(yaw=0.0, pitch=0.0, roll=0.0):
    """yaw: turn left (+), pitch: lean forward (+), roll: lean right (+)."""
    return (Matrix.Rotation(rad(yaw), 3, 'Z') @
            Matrix.Rotation(rad(-pitch), 3, 'X') @
            Matrix.Rotation(rad(roll), 3, 'Y'))


def euler_dir(az, el):
    """az: 0=fwd, +90=right ; el: +90=up, can exceed 90 (over the top)."""
    return (Matrix.Rotation(rad(-az), 3, 'Z') @
            Matrix.Rotation(rad(el), 3, 'X') @ Vector((0, 1, 0)))


def frame_from_euler(az, el, roll):
    """Rotation whose Y axis = direction(az, el), Z = 'up' side rolled."""
    return (Matrix.Rotation(rad(-az), 3, 'Z') @
            Matrix.Rotation(rad(el), 3, 'X') @
            Matrix.Rotation(rad(roll), 3, 'Y'))


def basis(x, y):
    """Orthonormal rotation from (approx) X and Y axes, Y exact."""
    y = y.normalized()
    x = (x - x.dot(y) * y).normalized()
    z = x.cross(y)
    return Matrix((x, y, z)).transposed()


def slerp_m(a, b, t):
    t = max(0.0, min(1.0, t))
    return a.to_quaternion().slerp(b.to_quaternion(), t).to_matrix()


def q_pow(m, t):
    q = m.to_quaternion()
    if q.w < 0:
        q.negate()
    return Quaternion().slerp(q, t).to_matrix()


def clamp(v, a, b):
    return max(a, min(b, v))


def smooth01(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------------------
# channel defaults (a neutral standing pose)
# --------------------------------------------------------------------------
DEFAULTS = dict(
    root_x=0.0, root_y=0.0, root_yaw=0.0,
    hips_x=0.0, hips_y=0.024, hips_z=0.848,
    hips_yaw=0.0, hips_pitch=0.0, hips_roll=0.0,
    sp_twist=0.0, sp_bend=0.0, sp_side=0.0,
    hd_yaw=0.0, hd_pitch=0.0, hd_roll=0.0, hd_abs=1.0,
    lsh_up=0.0, lsh_fwd=0.0, rsh_up=0.0, rsh_fwd=0.0,
    # right hand: grip point on a sphere around the posed right shoulder
    rh_r=0.24, rh_az=90.0, rh_el=-75.0,
    sw_az=0.0, sw_el=-60.0, sw_roll=0.0,
    rh_space=0.0, rh_fit=1.0,
    r_pole_x=0.4, r_pole_y=-0.6, r_pole_z=-1.0,
    # left hand
    lh_r=0.24, lh_az=-90.0, lh_el=-75.0,
    lhd_az=0.0, lhd_el=-80.0, lhd_roll=0.0,
    lh_space=0.0,
    l_pole_x=-0.4, l_pole_y=-0.6, l_pole_z=-1.0,
    # fingers
    r_curl=0.35, l_curl=0.35, l_spread=0.0, r_grip=0.0,
    # feet (ball of foot position, char space)
    lf_x=-0.108, lf_y=0.055, lf_z=0.0, lf_yaw=0.0, lf_lift=0.0, lf_space=0.0,
    rf_x=0.108, rf_y=0.055, rf_z=0.0, rf_yaw=0.0, rf_lift=0.0, rf_space=0.0,
    lk_out=0.0, rk_out=0.0,
    # sword
    sw_mat=0.0, sw_spin=0.0, sw_off=0.0,
)


class Rig:
    def __init__(self, arm):
        self.arm = arm
        self.obj_rot = arm.matrix_world.to_3x3().normalized()
        self.obj_scale = arm.matrix_world.to_scale()[0]
        self.q = {}      # rest rotation in char space
        self.h = {}      # rest head position in char space (m)
        self.tail = {}
        Kt = K.transposed()
        for b in arm.data.bones:
            Mw = arm.matrix_world @ b.matrix_local
            loc, rot, _ = Mw.decompose()
            self.q[b.name] = Kt @ rot.to_matrix()
            self.h[b.name] = Kt @ loc
            self.tail[b.name] = Kt @ (arm.matrix_world @ b.tail_local)
        self.parent = {b.name: (b.parent.name if b.parent else None)
                       for b in arm.data.bones}
        self.children = {b.name: [c.name for c in b.children] for b in arm.data.bones}
        self.order = [b.name for b in arm.data.bones]  # parents before children
        self._limb_setup()

    # ------------------------------------------------------------------
    def _limb_setup(self):
        h = self.h
        self.len = {}
        for s in ("Left", "Right"):
            self.len[s + "Arm"] = (h[P + s + "ForeArm"] - h[P + s + "Arm"]).length
            self.len[s + "Fore"] = (h[P + s + "Hand"] - h[P + s + "ForeArm"]).length
            self.len[s + "Thigh"] = (h[P + s + "Leg"] - h[P + s + "UpLeg"]).length
            self.len[s + "Shin"] = (h[P + s + "Foot"] - h[P + s + "Leg"]).length
        # rest hinge normals (char space).  n = pole x limb_dir
        # elbows: elbow points back (-y) while arm points out sideways.
        self.hinge0 = {
            "LeftArm": Vector((0, -1, 0)).cross(Vector((-1, 0, 0))),
            "RightArm": Vector((0, -1, 0)).cross(Vector((1, 0, 0))),
            "LeftUpLeg": Vector((0, 1, 0)).cross(Vector((0, 0, -1))),
            "RightUpLeg": Vector((0, 1, 0)).cross(Vector((0, 0, -1))),
        }
        # ball -> ankle offsets at rest
        self.ankle_from_ball = {
            s: h[P + s + "Foot"] - h[P + s + "ToeBase"] for s in ("Left", "Right")}
        # palm normal (hand local +Z) in char space, finger curl axes
        self.curl_axis = {}
        for s in ("Left", "Right"):
            palm = self.q[P + s + "Hand"] @ Vector((0, 0, 1))
            for f in FINGERS:
                for i in (1, 2, 3):
                    n = P + f"{s}Hand{f}{i}"
                    d = (self.tail[n] - self.h[n]).normalized()
                    if f == "Thumb" and i == 1:
                        # thumb root rolls the thumb under, towards the palm
                        ax = Vector((-1, 0, 0))
                    else:
                        ax = d.cross(palm)
                    self.curl_axis[n] = ax.normalized()
            self.palm = getattr(self, "palm", {})
            self.palm[s] = palm
        # sword grip definition, in RightHand local (rest) frame.
        qh = self.q[P + "RightHand"]
        hand_y = qh @ Vector((0, 1, 0))      # finger direction
        hand_z = qh @ Vector((0, 0, 1))      # palm normal (out of the palm)
        thumb = qh @ Vector((1, 0, 0))       # thumb side
        blade = (thumb * math.cos(rad(22)) + hand_y * math.sin(rad(22))).normalized()
        edge = hand_y - hand_y.dot(blade) * blade
        S_rest = basis(edge, blade)          # sword frame X=edge Y=blade
        grip_rest = (self.h[P + "RightHand"] + hand_y * 0.060 + hand_z * 0.021
                     + thumb * 0.004)
        self.sword_rest = S_rest
        self.grip_rest = grip_rest
        self.grip_rot_local = qh.transposed() @ S_rest
        self.grip_pos_local = qh.transposed() @ (grip_rest - self.h[P + "RightHand"])

    # ------------------------------------------------------------------
    def ensure_weapon_bone(self):
        arm = self.arm
        if WEAPON in arm.data.bones:
            return
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones
        b = eb.new(WEAPON)
        b.parent = eb[P + "RightHand"]
        inv = arm.matrix_world.inverted()
        head_w = K @ self.grip_rest
        blade_w = K @ (self.sword_rest @ Vector((0, 1, 0)))
        edge_w = K @ (self.sword_rest @ Vector((1, 0, 0)))
        b.head = inv @ head_w
        b.tail = inv @ (head_w + blade_w * 0.12)
        z_w = edge_w.cross(blade_w)
        b.align_roll(inv.to_3x3() @ z_w)
        bpy.ops.object.mode_set(mode='OBJECT')
        # refresh rest caches
        self.__init__(arm)

    # ------------------------------------------------------------------
    @staticmethod
    def two_bone(S, T, pole_dir, l1, l2, soft=0.94):
        """Return elbow position, hinge normal and effective end point.
        Soft IK: reach is compressed smoothly near full extension so the
        limb never snaps straight."""
        d = T - S
        dist = d.length
        a = d / max(dist, 1e-6)
        L = l1 + l2
        ds = L * soft
        if dist > ds:
            dist = ds + (L - ds) * (1.0 - math.exp(-(dist - ds) / (L - ds)))
        dist = clamp(dist, abs(l1 - l2) + 1e-4, L * 0.9995)
        cos_a = clamp((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1)
        alpha = math.acos(cos_a)
        p = pole_dir - pole_dir.dot(a) * a
        if p.length < 1e-5:
            p = Vector((0, 0, -1)) - a.z * a
        p.normalize()
        E = S + a * (l1 * math.cos(alpha)) + p * (l1 * math.sin(alpha))
        n = p.cross(a).normalized()
        return E, n, S + a * dist

    def limb_rot(self, bone, direction, hinge, hinge0):
        """Rotation (char space) for a limb bone given direction and hinge."""
        q = self.q[bone]
        d0 = q @ Vector((0, 1, 0))
        B0 = basis(hinge0, d0)
        B1 = basis(hinge, direction)
        return B1 @ B0.transposed() @ q

    # ------------------------------------------------------------------
    def solve(self, pose):
        c = dict(DEFAULTS)
        c.update(pose)
        R = {}   # posed rotation (char space) per bone
        H = {}   # posed head (char space) per bone
        G = {}   # aligned delta rotation per bone

        def place(name, g, head=None):
            G[name] = g
            R[name] = g @ self.q[name]
            if head is None:
                par = self.parent[name]
                head = H[par] + G[par] @ (self.h[name] - self.h[par])
            H[name] = head

        def place_rot(name, rot, head=None):
            place(name, rot @ self.q[name].transposed(), head)

        # ---- hips / spine -------------------------------------------
        Gh = ypr(c["hips_yaw"], c["hips_pitch"], c["hips_roll"])
        place(P + "Hips", Gh, Vector((c["hips_x"], c["hips_y"], c["hips_z"])))
        g = Gh
        for nm, f in (("Spine", 0.30), ("Spine1", 0.33), ("Spine2", 0.37)):
            g = g @ ypr(c["sp_twist"] * f, c["sp_bend"] * f, c["sp_side"] * f)
            place(P + nm, g)
        Gc = g
        # neck / head
        head_rel = ypr(c["hd_yaw"], c["hd_pitch"], c["hd_roll"])
        delta_abs = Gc.transposed() @ head_rel
        delta = slerp_m(head_rel, delta_abs, c["hd_abs"])
        gn = Gc @ q_pow(delta, 0.4)
        place(P + "Neck", gn)
        place(P + "Head", Gc @ delta)
        for nm in ("HeadTop_End", "HeadTop_End_end"):
            place(P + nm, G[self.parent[P + nm]])

        # ---- right arm (sword) -----------------------------------------
        self._last_gc = Gc
        sw_root = frame_from_euler(c["sw_az"], c["sw_el"], c["sw_roll"])
        S_char = slerp_m(sw_root, Gc @ sw_root, c["rh_space"])
        self._arm(c, "Right", Gc, S_char,
                  place, place_rot, H, G, is_sword=True)
        # ---- left arm ----------------------------------------------------
        L0 = basis(Vector((1, 0, 0)), Vector((0, 1, 0)))  # fingers fwd, x=thumb(right)
        Lh = frame_from_euler(c["lhd_az"], c["lhd_el"], c["lhd_roll"]) @ L0
        Lh = slerp_m(Lh, Gc @ Lh, c["lh_space"])
        self._arm(c, "Left", Gc, Lh, place, place_rot, H, G, is_sword=False)

        # ---- legs ----------------------------------------------------------
        for s, k in (("Left", "lf"), ("Right", "rf")):
            self._leg(c, s, k, Gh, place, place_rot, H, G)

        # ---- anything not yet placed: plain FK ---------------------------
        for nm in self.order:
            if nm not in G:
                place(nm, G[self.parent[nm]])

        self._sword_scale = smooth01(c["sw_mat"] * 3.0)
        return R, H, G

    # ------------------------------------------------------------------
    def _arm(self, c, s, Gc, frame, place, place_rot, H, G, is_sword):
        pre = "r" if s == "Right" else "l"
        side = 1 if s == "Right" else -1
        # clavicle: manual + automatic shrug when hand goes high / forward
        el = c[pre + "h_el"]
        auto_up = clamp((el + 10) / 100.0, 0, 1) * 22.0
        up = c[pre + "sh_up"] + auto_up
        fwd = c[pre + "sh_fwd"]
        g_sh = Gc @ axis_rot((0, -side, 0), up) @ axis_rot((0, 0, side), fwd)
        place(P + s + "Shoulder", g_sh)
        Sj = H[P + s + "Shoulder"] + g_sh @ (self.h[P + s + "Arm"] - self.h[P + s + "Shoulder"])

        # target (grip point for the sword hand, palm point for the left hand)
        dirv = euler_dir(c[pre + "h_az"], el)
        dirv_c = Gc @ dirv
        sp = c[pre + "h_space"]
        dirv = (dirv * (1 - sp) + dirv_c * sp).normalized()
        T = Sj + dirv * c[pre + "h_r"]

        q_hand = self.q[P + s + "Hand"]
        if is_sword:
            R_hand = frame @ self.grip_rot_local.transposed()
            off = self.grip_pos_local
        else:
            # left: frame is the hand frame (Y=fingers, X=thumb side, Z=back of hand)
            # map to rest hand: rest left hand Y=fingers, Z=palm normal, X=-thumb
            rest_frame = basis(-(q_hand @ Vector((1, 0, 0))), q_hand @ Vector((0, 1, 0)))
            R_hand = frame @ rest_frame.transposed() @ q_hand
            off = Vector((0, 0.035, 0.0))          # palm centre offset (hand local)

        pole = Vector((c[pre + "_pole_x"], c[pre + "_pole_y"], c[pre + "_pole_z"]))
        pole_c = Gc @ pole
        pole = (pole * (1 - sp) + pole_c * sp).normalized()
        l1, l2 = self.len[s + "Arm"], self.len[s + "Fore"]
        limit = 68.0 if is_sword else 50.0
        auto_w = 0.55
        if is_sword:
            self.fit_info = (T, T, Sj)
        if is_sword and c.get("rh_fit", 1.0) > 0.5:
            # Keep the blade on its authored path: when the wrist would have
            # to bend past its range, move the grip towards the spot where the
            # wrist is straight (sphere of radius l1 around the implied elbow
            # pivot) instead of rotating the sword.  Blended by how far over
            # the range the first solve is, so it stays continuous.
            T = self._fit_grip(T, Sj, R_hand, off, pole, l1, l2, limit, auto_w)
        for _ in range(4):
            wrist = T - R_hand @ off
            f_star = R_hand @ Vector((0, 1, 0))        # forearm dir for a neutral wrist
            e_star = (wrist - f_star * l2) - Sj
            pole_use = pole
            if e_star.length > 1e-5:
                pole_use = (pole * (1 - auto_w) + e_star.normalized() * auto_w)
            E, n, w_eff = self.two_bone(Sj, wrist, pole_use, l1, l2, soft=0.93)
            fore_dir = (w_eff - E).normalized()
            bend = math.degrees(fore_dir.angle(f_star))
            if bend <= limit:
                break
            axis = f_star.cross(fore_dir)
            if axis.length < 1e-6:
                break
            R_hand = Matrix.Rotation(math.radians(bend - limit), 3, axis.normalized()) @ R_hand
        r_up = self.limb_rot(P + s + "Arm", (E - Sj).normalized(), n, self.hinge0[s + "Arm"])
        place_rot(P + s + "Arm", r_up, Sj)
        r_fore = self.limb_rot(P + s + "ForeArm", fore_dir, n, self.hinge0[s + "Arm"])
        # distribute hand twist into the forearm (no twist bones on this rig)
        rel = (r_fore.transposed() @ R_hand)
        qrel = rel.to_quaternion()
        tw = Quaternion((qrel.w, 0, qrel.y, 0))
        if tw.magnitude > 1e-6:
            tw.normalize()
            ang = 2 * math.atan2(tw.y, tw.w)
            ang = (ang + math.pi) % (2 * math.pi) - math.pi
            r_fore = r_fore @ Matrix.Rotation(ang * 0.6, 3, 'Y')
        place_rot(P + s + "ForeArm", r_fore, E)
        wrist_real = w_eff
        place_rot(P + s + "Hand", R_hand, wrist_real)
        self._fingers(c, s, H, G, place)
        if is_sword:
            Gw = G[P + "RightHand"]
            spin = axis_rot(R_hand @ Vector((0, 0, 1)), c["sw_spin"])
            # rotate about the grip point
            # sw_off slides the sword out of the palm (keeps twirls clear of the forearm)
            grip_now = H[P + "RightHand"] + R_hand @ (self.grip_pos_local + Vector((0, 0, c["sw_off"])))
            g_w = spin @ Gw
            place(WEAPON, g_w, grip_now + spin @ (Gw @ (self.h[WEAPON] - self.grip_rest)))

    def _wrist_bend(self, T, Sj, R_hand, off, pole, l1, l2, auto_w):
        wrist = T - R_hand @ off
        f_star = R_hand @ Vector((0, 1, 0))
        e_star = (wrist - f_star * l2) - Sj
        pole_use = pole
        if e_star.length > 1e-5:
            pole_use = (pole * (1 - auto_w) + e_star.normalized() * auto_w)
        E, n, w_eff = self.two_bone(Sj, wrist, pole_use, l1, l2, soft=0.93)
        fore_dir = (w_eff - E).normalized()
        return math.degrees(fore_dir.angle(f_star))

    def _fit_grip(self, T, Sj, R_hand, off, pole, l1, l2, limit, auto_w):
        self.fit_info = (T, T, Sj)
        bend = self._wrist_bend(T, Sj, R_hand, off, pole, l1, l2, auto_w)
        x = (bend - (limit - 12.0)) / 20.0
        w = smooth01(x)
        if w <= 0.0:
            return T
        f_star = R_hand @ Vector((0, 1, 0))
        C = Sj + f_star * l2 + R_hand @ off
        d = T - C
        if d.length < 1e-6:
            return T
        T_fit = C + d.normalized() * (l1 * 0.97)
        shift = (T_fit - T) * w
        if shift.length > 0.07:                     # never drag the hand far
            shift = shift * (0.07 / shift.length)
        T_new = T + shift
        # keep a sensible reach (don't fold the arm into the shoulder)
        reach = (T_new - Sj).length
        r_min = min((T - Sj).length, 0.62 * (l1 + l2 + off.length))
        if reach < r_min:
            T_new = Sj + (T_new - Sj) * (r_min / max(reach, 1e-6))
        self.fit_info = (T, T_new, Sj)
        return T_new

    def fit_sword_grip(self, T, sigma=1.6, passes=1):
        for _ in range(passes):
            self._fit_pass(T, sigma)
        # the correction is now part of the curves: no per-frame refit
        f0, data = T._cache
        data["rh_fit"] = [0.0] * len(data["rh_r"])

    def _fit_pass(self, T, sigma):
        """Bake the grip fit into the timeline's rh_az / rh_el / rh_r curves,
        so the hand placement that keeps the blade on its path is smooth in
        time.  The correction is low-passed as a 3D offset (well defined even
        with the hand straight overhead) and only frames it touches change.
        Needs T.bake_cache() to have run."""
        from timeline import Timeline as _TL
        f0, data = T._cache
        n = len(data["rh_r"])
        orig, delta = [], []
        for i in range(n):
            c = dict(DEFAULTS)
            c.update({ch: arr[i] for ch, arr in data.items()})
            c["rh_fit"] = 1.0
            self.solve(c)
            T0, T1, Sj = self.fit_info
            sp = clamp(c["rh_space"], 0.0, 1.0)
            Gc = self._last_gc
            # keyed-space vector: v such that blend(v) * r = target - shoulder
            v0 = euler_dir(c["rh_az"], c["rh_el"]) * c["rh_r"]
            d1 = T1 - Sj
            r1 = d1.length
            u = d1 / max(r1, 1e-9)
            if sp > 1e-4:
                # invert dir = normalize(v (1 - sp) + Gc v sp)
                v = u.copy()
                for _ in range(4):
                    cur = (v * (1 - sp) + (Gc @ v) * sp).normalized()
                    v = cur.rotation_difference(u).to_matrix() @ v
                u = v.normalized()
            orig.append(v0)
            delta.append(u * r1 - v0)
        dx = _TL._gauss([d.x for d in delta], sigma)
        dy = _TL._gauss([d.y for d in delta], sigma)
        dz = _TL._gauss([d.z for d in delta], sigma)
        for i in range(n):
            dd = Vector((dx[i], dy[i], dz[i]))
            if dd.length < 1e-5:
                continue
            w = orig[i] + dd
            r = w.length
            w = w / max(r, 1e-9)
            el = math.degrees(math.asin(clamp(w.z, -1.0, 1.0)))
            az = math.degrees(math.atan2(w.x, w.y))
            # stay on the Euler branch / turn count of the keyed curve
            oa, oe = data["rh_az"][i], data["rh_el"][i]
            best = None
            for ca, ce in ((az, el), (az + 180.0, 180.0 - el), (az + 180.0, -180.0 - el)):
                ca += 360.0 * round((oa - ca) / 360.0)
                ce += 360.0 * round((oe - ce) / 360.0)
                cost = abs(ca - oa) + abs(ce - oe)
                if best is None or cost < best[0]:
                    best = (cost, ca, ce)
            data["rh_az"][i], data["rh_el"][i], data["rh_r"][i] = best[1], best[2], r

    # ------------------------------------------------------------------
    def _fingers(self, c, s, H, G, place):
        pre = "r" if s == "Right" else "l"
        curl = c[pre + "_curl"]
        spread = c.get(pre + "_spread", 0.0)
        gh = G[P + s + "Hand"]
        # per-joint curl angles for a full fist
        fist = {1: 72.0, 2: 95.0, 3: 55.0}
        relaxed_extra = {"Index": 0.85, "Middle": 1.0, "Ring": 1.1, "Pinky": 1.2}
        spreads = {"Index": -1.0, "Middle": 0.0, "Ring": 1.0, "Pinky": 2.0}
        palm = self.palm[s]
        for f in FINGERS:
            g = gh
            for i in (1, 2, 3):
                n = P + f"{s}Hand{f}{i}"
                if f == "Thumb":
                    ang = {1: 22.0, 2: 30.0, 3: 40.0}[i] * curl
                    rot = axis_rot(self.curl_axis[n], ang)
                    if i == 1:
                        rot = rot @ axis_rot(palm, (1 if s == "Right" else -1) * 28.0 * curl)
                else:
                    k = relaxed_extra[f] if curl < 0.6 else 1.0
                    ang = fist[i] * curl * k
                    rot = axis_rot(self.curl_axis[n], ang)
                    if i == 1 and spread:
                        rot = rot @ axis_rot(palm, spreads[f] * spread * 6.0 * (1 if s == "Right" else -1))
                g = g @ rot
                place(n, g)

    # ------------------------------------------------------------------
    def _leg(self, c, s, k, Gh, place, place_rot, H, G):
        side = 1 if s == "Right" else -1
        ball = Vector((c[k + "_x"], c[k + "_y"], c[k + "_z"]))
        yaw = c[k + "_yaw"]
        lift = c[k + "_lift"]
        # heel lift: pivot about the ball, around the foot's lateral axis
        Ry = ypr(yaw)
        lat = Ry @ Vector((1, 0, 0))
        Rl = axis_rot(lat, -lift)
        Rfoot = Rl @ Ry
        sp = c[k + "_space"]
        if sp > 0:
            hips_rest = Vector((DEFAULTS["hips_x"], DEFAULTS["hips_y"], DEFAULTS["hips_z"]))
            ball_h = H[P + "Hips"] + Gh @ (ball - hips_rest)
            Rfoot_h = Gh @ Rfoot
            ball = ball * (1 - sp) + ball_h * sp
            Rfoot = slerp_m(Rfoot, Rfoot_h, sp)
        ankle = ball + Rfoot @ self.ankle_from_ball[s]
        Hj = H[P + "Hips"] + Gh @ (self.h[P + s + "UpLeg"] - self.h[P + "Hips"])
        fwd = Rfoot @ Vector((0, 1, 0))
        hips_fwd = Gh @ Vector((0, 1, 0))
        knee_dir = (fwd * 0.6 + hips_fwd * 0.4)
        knee_dir = axis_rot(Rfoot @ Vector((0, 0, 1)), -side * (8.0 + c[k[0] + "k_out"])) @ knee_dir
        l1, l2 = self.len[s + "Thigh"], self.len[s + "Shin"]
        E, n, _ = self.two_bone(Hj, ankle, knee_dir, l1, l2, soft=0.985)
        r_th = self.limb_rot(P + s + "UpLeg", (E - Hj).normalized(), n, self.hinge0[s + "UpLeg"])
        place_rot(P + s + "UpLeg", r_th, Hj)
        sh_dir = (ankle - E).normalized()
        r_sh = self.limb_rot(P + s + "Leg", sh_dir, n, self.hinge0[s + "UpLeg"])
        place_rot(P + s + "Leg", r_sh, E)
        ankle_real = E + sh_dir * l2
        place(P + s + "Foot", Rfoot, ankle_real)
        # toes stay flat while the ball is planted
        flat = clamp(1.0 - c[k + "_z"] / 0.05, 0.0, 1.0) * (1 - sp)
        g_toe = slerp_m(Rfoot, Ry, flat)
        place(P + s + "ToeBase", g_toe)

    # ------------------------------------------------------------------
    def to_world(self, c, R, H):
        """char-space results -> world rotation / position dicts."""
        Rz = Matrix.Rotation(rad(c.get("root_yaw", 0.0)), 3, 'Z')
        off = Vector((c.get("root_x", 0.0), c.get("root_y", 0.0), 0.0))
        Wr, Wp = {}, {}
        for n in R:
            Wr[n] = K @ Rz @ R[n]
            Wp[n] = K @ (Rz @ H[n] + off)
        return Wr, Wp

    def apply(self, pose):
        """Solve and write matrix_basis to every pose bone. Returns world data."""
        c = dict(DEFAULTS)
        c.update(pose)
        R, H, G = self.solve(c)
        Wr, Wp = self.to_world(c, R, H)
        arm = self.arm
        inv_rot = self.obj_rot.transposed()
        s = self.obj_scale
        A = {}
        for n in self.order:
            rot = inv_rot @ Wr[n]
            loc = inv_rot @ Wp[n] / s
            M = rot.to_4x4()
            M.translation = loc
            if n == WEAPON:
                v = max(self._sword_scale, 1e-4)
                M = M @ Matrix.Diagonal((v, v, v, 1.0))
            A[n] = M
        for n in self.order:
            b = arm.data.bones[n]
            pb = arm.pose.bones[n]
            par = self.parent[n]
            if par is None:
                basis_m = b.matrix_local.inverted() @ A[n]
            else:
                rest_rel = arm.data.bones[par].matrix_local.inverted() @ b.matrix_local
                basis_m = rest_rel.inverted() @ A[par].inverted() @ A[n]
            pb.matrix_basis = basis_m
        return c, Wr, Wp
