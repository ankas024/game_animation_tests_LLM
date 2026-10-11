"""The character's performance for VIGIL, generated procedurally and baked to keys.

Beats (24 fps)
    1-40     stands in the west doorway, gathers herself, lifts her gaze
    40-430   walks down the nave (footstep-planned gait, IK feet)
    ~430     slows to a stop in the moonbeam
    440-500  looks up at the broken vault and the moon
    520-580  raises her right hand into the light, fingers spread
    630-660  closes her hand - "catches" the light
    660-720  draws the fist to her chest, gaze lowers, then lifts ahead
"""

import math

import numpy as np
from mathutils import Matrix, Quaternion, Vector

from character import P, UNIT, Rig, frame_rot, look_rot, qx, qy, qz

FPS = 24
FRAME_END = 840


# --------------------------------------------------------------------------- helpers

def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smooth(x):
    x = clamp01(x)
    return x * x * x * (x * (x * 6 - 15) + 10)


def mix(a, b, t):
    return a + (b - a) * t


def mir(q):
    """Mirror a left-side rotation to the right side (reflect through X=0)."""
    return Quaternion((q.w, q.x, -q.y, -q.z))


class Curve:
    """Move-and-hold keyframe curve with smootherstep easing between keys."""

    def __init__(self, keys):
        self.keys = sorted(keys, key=lambda k: k[0])

    def __call__(self, f):
        k = self.keys
        if f <= k[0][0]:
            return k[0][1]
        if f >= k[-1][0]:
            return k[-1][1]
        for (f0, v0), (f1, v1) in zip(k, k[1:]):
            if f0 <= f <= f1:
                return mix(v0, v1, smooth((f - f0) / (f1 - f0)))


def wobble(f, seed, period, amp):
    """Cheap organic noise: three incommensurate sines."""
    t = f / FPS
    return amp * (0.6 * math.sin(2 * math.pi * t / period + seed)
                  + 0.3 * math.sin(2 * math.pi * t / (period * 0.37) + seed * 2.3)
                  + 0.1 * math.sin(2 * math.pi * t / (period * 0.13) + seed * 5.1))


def gauss_smooth(arr, sigma):
    r = int(sigma * 3) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(arr, (r, r), mode="edge")
    return np.convolve(pad, k, mode="valid")


# --------------------------------------------------------------------------- performance

class Performance:
    # world placement
    START_Y = -21.7           # world Y of her first stance (standing in the west doorway)

    # gait
    T_WALK = 40
    T_STOP = 430
    RAMP_UP = 22
    RAMP_DOWN = 46
    WALK_MPS = 1.08
    STEP = 14                 # frames per step (28-frame cycle)
    SWING = 11                # frames each foot spends in the air

    W_WALK = 5.0              # lateral foot placement (armature units, ~7 cm)
    W_STAND = 7.5

    ANKLE_H = 5.7
    BALL_Z = 5.6
    HEEL_Z = 3.0

    def __init__(self, rig: Rig, arm_obj, frame_end=FRAME_END):
        self.rig = rig
        self.arm = arm_obj
        self.frame_end = frame_end
        self.mw = Matrix.LocRotScale(Vector((0, self.START_Y, 0)),
                                     arm_obj.rotation_euler.to_quaternion(),
                                     Vector((UNIT, UNIT, UNIT)))
        self.mw_inv = self.mw.inverted()
        self.v = self.WALK_MPS / FPS / UNIT
        self._build_progress()
        self._plan_steps()
        self.L1 = rig.bone_len(P + "LeftUpLeg", P + "LeftLeg")
        self.L2 = rig.bone_len(P + "LeftLeg", P + "LeftFoot")
        self._build_pelvis()
        self.track = {}       # frame -> dict of world positions (filled by bake)
        self.contacts = []    # (frame, foot, world pos) heel strikes for the soundtrack

    # ---- coordinate helpers
    def to_arm(self, p):
        return self.mw_inv @ Vector(p)

    def to_world(self, p):
        return self.mw @ p

    # ---- pelvis progress along the nave
    def speed(self, t):
        up = smooth((t - self.T_WALK) / self.RAMP_UP)
        down = 1 - smooth((t - (self.T_STOP - self.RAMP_DOWN)) / self.RAMP_DOWN)
        return self.v * up * down

    def _build_progress(self):
        dt = 0.05
        self._tt = np.arange(-60, self.frame_end + 60, dt)
        sp = np.array([self.speed(t) for t in self._tt])
        self._ss = np.cumsum(sp) * dt
        self.s_final = float(self._ss[-1])

    def s(self, t):
        return float(np.interp(t, self._tt, self._ss))

    @property
    def stop_world_y(self):
        return self.START_Y + self.s_final * UNIT

    # ---- footstep planning
    def _plan_steps(self):
        stance = {  # final stance: slight stagger, toes out, weight to the right
            "L": (self.s_final + 3.5, self.W_STAND + 0.5, 9.0),
            "R": (self.s_final - 2.0, -self.W_STAND - 0.5, -15.0),
        }
        self.plants = {"L": [(-1e9, 0.0, self.W_STAND, 6.0)],
                       "R": [(-1e9, 0.0, -self.W_STAND, -8.0)]}
        self.steps = {"L": [], "R": []}
        k = 0
        while True:
            lift = self.T_WALK + 3 + k * self.STEP
            foot = "R" if k % 2 == 0 else "L"
            side = -1 if foot == "R" else 1
            contact = lift + self.SWING
            z = self.s(contact + 0.5 * self.STEP)
            sf = self.speed(contact) / self.v
            x = side * mix(self.W_STAND, self.W_WALK, sf)
            yaw = side * mix(7.0, 4.0, sf)
            prev = self.plants[foot][-1]
            if abs(z - prev[1]) > 2.5:
                self.steps[foot].append(dict(lift=lift, contact=contact,
                                             frm=prev[1:], to=(z, x, yaw)))
                self.plants[foot].append((contact, z, x, yaw))
            if lift > self.T_STOP and all(abs(self.plants[f][-1][1] - self.s_final) < 4 for f in "LR"):
                break
            k += 1
            if k > 500:
                raise RuntimeError("footstep planner did not converge")
        for f in "LR":
            last = self.steps[f][-1]
            last["to"] = stance[f]
            self.plants[f][-1] = (last["contact"],) + stance[f]
        # fix chained 'frm' after the stance override
        for f in "LR":
            for a, b in zip(self.steps[f], self.steps[f][1:]):
                b["frm"] = a["to"]

    def step_scale(self, st):
        return clamp01(abs(st["to"][0] - st["frm"][0]) / (2 * self.v * self.STEP))

    def foot_state(self, foot, t):
        """Return (ground point under ankle, pitch deg, yaw deg, lift, toe_bend, loaded)."""
        prev_to = self.plants[foot][0][1:]
        last_contact, last_sc = -1e9, 1.0
        for st in self.steps[foot]:
            sc = self.step_scale(st)
            if t < st["lift"]:
                # planted at prev_to: heel slap after the last contact, heel-off before lift
                tau = t - last_contact
                pitch = -14.0 * last_sc * (1 - smooth(tau / 3.5)) if tau < 4 else 0.0
                tau2 = st["lift"] - t
                if tau2 < 7:
                    pitch = max(pitch, 30.0 * sc * (1 - tau2 / 7) ** 2)
                z, x, yaw = prev_to
                return Vector((x, 0, z)), pitch, yaw, 0.0, max(pitch, 0.0), True
            if t < st["contact"]:
                u = (t - st["lift"]) / (st["contact"] - st["lift"])
                e = u - math.sin(2 * math.pi * u) / (2 * math.pi)
                (z0, x0, y0), (z1, x1, y1) = st["frm"], st["to"]
                g = Vector((mix(x0, x1, e), 0, mix(z0, z1, e)))
                pitch = Curve([(0, 30.0 * sc), (0.45, 2.0), (0.85, -14.0 * sc), (1.0, -14.0 * sc)])(u)
                lift = 6.5 * sc * math.sin(math.pi * u ** 0.8)
                toe = 30.0 * sc * max(0.0, 1 - u / 0.35)
                return g, pitch, mix(y0, y1, e), lift, toe, False
            prev_to, last_contact, last_sc = st["to"], st["contact"], sc
        z, x, yaw = prev_to
        tau = t - last_contact
        pitch = -14.0 * last_sc * (1 - smooth(tau / 3.5)) if tau < 4 else 0.0
        return Vector((x, 0, z)), pitch, yaw, 0.0, 0.0, True

    def ankle_from_ground(self, g, pitch, yaw, lift):
        qyaw = qy(yaw)
        if pitch >= 0:   # heel up: pivot on the ball of the foot
            pivot = g + qyaw @ Vector((0, 0, self.BALL_Z))
            rel = Vector((0, self.ANKLE_H, -self.BALL_Z))
        else:            # toe up: pivot on the heel
            pivot = g + qyaw @ Vector((0, 0, -self.HEEL_Z))
            rel = Vector((0, self.ANKLE_H, self.HEEL_Z))
        return pivot + qyaw @ (qx(pitch) @ rel) + Vector((0, lift, 0))

    # ---- pelvis trajectory (two passes so it can respect leg reach)
    def _build_pelvis(self):
        frames = np.arange(1, self.frame_end + 1)
        hips0 = self.rig.head0[P + "Hips"]
        reach = (self.L1 + self.L2) * 0.982
        base = hips0.y - 1.6
        ys, sx = [], []
        for f in frames:
            lim = base
            sup, wsum = 0.0, 0.0
            z = self.s(f)
            for foot, side in (("L", 1), ("R", -1)):
                g, pitch, yaw, lift, toe, loaded = self.foot_state(foot, f)
                a = self.ankle_from_ground(g, pitch, yaw, lift)
                if loaded:
                    hip = Vector((side * 6.7, 0, z))
                    dxz = math.hypot(hip.x - a.x, hip.z - a.z)
                    lim = min(lim, a.y + math.sqrt(max(reach ** 2 - dxz ** 2, 1.0)) + 2.43)
                    w = 1.0 if pitch <= 5 else 0.5
                    sup += a.x * w
                    wsum += w
            ys.append(lim)
            sx.append(sup / wsum if wsum else 0.0)
        ys = np.array(ys)
        ys_s = gauss_smooth(ys, 1.6)
        self.hips_y = np.minimum(ys_s, ys + 0.4)
        self.hips_y = gauss_smooth(self.hips_y, 0.8)
        self.support_x = gauss_smooth(np.array(sx), 3.5)

    # --------------------------------------------------------------------------- bake
    def bake(self, sky_target_world):
        """Key every frame. ``sky_target_world`` is where she looks up to (the broken vault)."""
        rig = self.rig
        self.sky_target = sky = self.to_arm(sky_target_world)
        sf_final = self.s_final

        # gaze: relative-to-walker targets blend into absolute targets near the end
        look_rel = Curve([
            (1, Vector((0, 30, 120))), (16, Vector((0, 30, 120))),
            (36, Vector((0, 150, 700))), (196, Vector((0, 130, 700))),
            (220, Vector((-330, 420, 450))), (252, Vector((-330, 420, 450))),   # moonlit windows, her right
            (276, Vector((0, 120, 700))), (288, Vector((0, 120, 700))),
            (304, Vector((92, 6, 160))), (326, Vector((92, 6, 160))),       # candles by the pews, her left
            (350, Vector((0, 140, 700))), (420, Vector((0, 260, 600))),
        ])
        hand_target = self.reach_target()
        fist_target = Vector((-2.5, 99.0, sf_final + 14.0))
        look_abs = Curve([
            (420, sky), (580, sky),
            (604, hand_target + Vector((0, 4, 0))), (640, hand_target + Vector((0, 4, 0))),
            (668, fist_target + Vector((0, -6, 8))), (712, fist_target + Vector((0, -6, 8))),
            (742, Vector((0, 150, sf_final + 900))),
        ])
        look_abs_w = Curve([(418, 0.0), (452, 1.0)])

        chest_up = Curve([(430, 0.0), (468, 1.0), (590, 1.0), (620, 0.35), (668, -0.15),
                          (712, -0.15), (745, 0.15)])
        reach_w = Curve([(512, 0.0), (566, 1.0), (668, 1.0), (708, 0.0)])
        fist_w = Curve([(660, 0.0), (700, 1.0), (745, 1.0), (775, 0.6)])
        grip = Curve([(520, 0.2), (560, -0.25), (628, -0.25), (652, 1.0)])
        breath_amp = Curve([(1, 1.0), (40, 0.6), (430, 0.8), (470, 1.6), (560, 1.0), (640, 2.2),
                            (700, 1.2)])
        weight_shift = Curve([(430, 0.0), (470, 1.0)])
        doorway_slump = Curve([(1, 1.0), (30, 0.0)])

        for f in range(1, self.frame_end + 1):
            Q = {}
            i = f - 1
            z = self.s(f)
            sfac = self.speed(f) / self.v
            sfac_l = self.speed(f - 4) / self.v

            # --- feet
            feet = {}
            for foot in "LR":
                g, pitch, yaw, lift, toe, loaded = self.foot_state(foot, f)
                feet[foot] = (self.ankle_from_ground(g, pitch, yaw, lift), pitch, yaw, toe, loaded, g)
            zl, zr = feet["L"][5].z, feet["R"][5].z
            stride = 2 * self.v * self.STEP
            phase_diff = max(-1.0, min(1.0, (zl - zr) / (0.5 * stride)))

            # --- pelvis
            ws = weight_shift(f)
            idle_sway = wobble(f, 0.7, 5.5, 0.6) * (1 - sfac)
            hx = 0.5 * self.support_x[i] + idle_sway - 2.2 * ws
            hy = self.hips_y[i] - 0.5 * doorway_slump(f) + wobble(f, 2.1, 4.0, 0.15)
            hips_pos = Vector((hx, hy, z + 0.6 * sfac))
            yaw_p = -6.0 * phase_diff * sfac + 3.0 * ws
            roll_p = 4.5 * (self.support_x[i] / self.W_WALK) * sfac + wobble(f, 1.3, 6.0, 0.6) - 3.0 * ws
            pitch_p = 3.0 * sfac + 1.0
            Q[P + "Hips"] = qy(yaw_p) @ qz(roll_p) @ qx(pitch_p)

            # --- spine: counter-rotation, breathing, chest lift
            t = f / FPS
            br = math.sin(2 * math.pi * t / mix(3.8, 2.6, sfac)) * breath_amp(f)
            cu = chest_up(f)
            reach = reach_w(f)
            slump = doorway_slump(f)
            spine_pitch = [-0.5 * sfac + 1.2 * slump - 2.2 * cu,
                           -0.4 * br - 2.8 * cu + 1.4 * slump,
                           -0.6 * br - 3.2 * cu + 1.0 * slump]
            for name, yk, rk, pp in (("Spine", -0.35, -0.5, spine_pitch[0]),
                                     ("Spine1", -0.5, -0.35, spine_pitch[1]),
                                     ("Spine2", -0.55, -0.25, spine_pitch[2])):
                Q[P + name] = qy(yk * yaw_p - 2.5 * reach * (name == "Spine2")) \
                    @ qz(rk * roll_p + 1.5 * reach * (name != "Spine")) @ qx(pp)

            # --- shoulders
            pd_lag = self._phase_diff(f - 3)
            swing_l = -15.0 * pd_lag * sfac_l   # left arm forward when the right foot leads
            swing_r = 15.0 * pd_lag * sfac_l
            sh = 0.5 * br - 1.0 * slump
            Q[P + "LeftShoulder"] = qz(sh) @ qy(-0.12 * swing_l)
            Q[P + "RightShoulder"] = mir(qz(sh + 9.0 * reach) @ qy(-0.12 * swing_r))
            down = 73.0
            for side, sw in (("Left", swing_l), ("Right", swing_r)):
                q_arm = qx(-(4.0 + sw)) @ qz(-down) @ qy(-6.0)
                elbow = 16.0 + 10.0 * max(0.0, sw / 15.0) + 4.0 * slump
                q_fore = qy(-elbow)
                q_hand = qz(-8.0) @ qy(-6.0)
                if side == "Right":
                    q_arm, q_fore, q_hand = mir(q_arm), mir(q_fore), mir(q_hand)
                Q[P + side + "Arm"] = q_arm
                Q[P + side + "ForeArm"] = q_fore
                Q[P + side + "Hand"] = q_hand

            # --- fingers (relaxed curl, spread on reach, fist at the end)
            self._fingers(Q, "Left", 0.2)
            self._fingers(Q, "Right", grip(f) if f >= 520 else 0.2)

            # --- FK pass to find joint roots, then IK legs/arm
            delta, head = rig.fk(Q, hips_pos)
            for foot, side, name in (("L", 1, "Left"), ("R", -1, "Right")):
                a, pitch, yaw, toe, loaded, gpt = feet[foot]
                pole = qy(yaw_p) @ Vector((0.15 * side, 0.0, 1.0))
                end_delta = qy(yaw) @ qx(pitch)
                rig.two_bone(Q, delta, head, P + name + "UpLeg", P + name + "Leg", P + name + "Foot",
                             a, pole, Vector((0, 0, 1)), end_delta=end_delta)
                Q[P + name + "ToeBase"] = qx(-toe)

            if reach > 0 or fist_w(f) > 0:
                delta, head = rig.fk(Q, hips_pos)
                self._right_arm_ik(Q, delta, head, f, reach, fist_w(f), hand_target, fist_target)

            # --- head & neck look-at
            delta, head = rig.fk(Q, hips_pos)
            lr = look_rel(f)
            tgt_rel = Vector((lr.x, lr.y, z + lr.z))
            w_abs = look_abs_w(f)
            tgt = tgt_rel.lerp(look_abs(f), w_abs) if w_abs > 0 else tgt_rel
            hpos = head[P + "Head"]
            d = (tgt - hpos).normalized()
            # human necks can't look straight up: limit pitch
            pitch_up = math.degrees(math.asin(max(-1, min(1, d.y))))
            if pitch_up > 48:
                flat = Vector((d.x, 0, d.z)).normalized()
                a = math.radians(48)
                d = flat * math.cos(a) + Vector((0, math.sin(a), 0))
            want = look_rot(d, Vector((0, 1, 0)))
            want = want @ qz(wobble(f, 4.2, 7.0, 1.2) + 4.0 * reach - 5.0 * fist_w(f) * (f < 720))
            relq = delta[P + "Spine2"].inverted() @ want
            q_neck = Quaternion().slerp(relq, 0.45)
            Q[P + "Neck"] = q_neck
            Q[P + "Head"] = q_neck.inverted() @ relq

            rig.apply(Q, hips_pos, frame=f)

            # --- tracking data for cameras / sound
            delta, head = rig.fk(Q, hips_pos)
            self.track[f] = {
                "hips": self.to_world(head[P + "Hips"]),
                "head": self.to_world(head[P + "Head"] + delta[P + "Head"] @ Vector((0, 8, 1))),
                "chest": self.to_world(head[P + "Spine2"]),
                "rhand": self.to_world(head[P + "RightHand"]),
                "lfoot": self.to_world(head[P + "LeftFoot"]),
                "rfoot": self.to_world(head[P + "RightFoot"]),
            }
        for foot in "LR":
            for st in self.steps[foot]:
                z, x, _ = st["to"]
                self.contacts.append((st["contact"], foot, self.to_world(Vector((x, 0, z))),
                                      self.step_scale(st)))
        self.contacts.sort(key=lambda c: c[0])

    def _phase_diff(self, f):
        gl = self.foot_state("L", f)[0]
        gr = self.foot_state("R", f)[0]
        stride = 2 * self.v * self.STEP
        return max(-1.0, min(1.0, (gl.z - gr.z) / (0.5 * stride)))

    def _fingers(self, Q, side, curl):
        """curl: ~0.2 relaxed, 1 = fist, negative = opened and spread."""
        for i, finger in enumerate(("Index", "Middle", "Ring", "Pinky")):
            relaxed = 6.0 + 3.0 * i
            spread = (i - 1.5) * 7.0 * clamp01(-curl / 0.25)
            for j in (1, 2, 3):
                rest_a = relaxed + 5.0 * j
                if curl >= 0.2:
                    a = mix(rest_a, (78, 98, 66)[j - 1], clamp01((curl - 0.2) / 0.8))
                else:
                    a = mix(rest_a, -3.0, clamp01((0.2 - curl) / 0.45))
                q = qz(-a)
                if j == 1:
                    q = qy(spread) @ q
                Q[P + f"{side}Hand{finger}{j}"] = mir(q) if side == "Right" else q
        # thumb: opposition rolls it under the palm (about the hand's long axis, +X),
        # flexion bends it about an axis perpendicular to the thumb in the palm plane
        tc = clamp01((curl - 0.2) / 0.8)
        op = clamp01((0.2 - curl) / 0.45)
        flex = Vector((0.465, 0.0, -0.885))
        thumbs = [qx(10 + 48 * tc - 10 * op) @ Quaternion(flex, math.radians(6 + 16 * tc - 6 * op)),
                  Quaternion(flex, math.radians(10 + 32 * tc - 8 * op)),
                  Quaternion(flex, math.radians(8 + 38 * tc - 8 * op))]
        for j, q in enumerate(thumbs, 1):
            Q[P + f"{side}HandThumb{j}"] = mir(q) if side == "Right" else q

    def reach_target(self):
        """Right hand target for the reach, in armature space."""
        sh = self.rig.head0[P + "RightArm"]
        d = Vector((-0.28, 0.78, 0.56)).normalized()
        L = self.rig.bone_len(P + "RightArm", P + "RightForeArm") + \
            self.rig.bone_len(P + "RightForeArm", P + "RightHand")
        return Vector((sh.x, sh.y + 2.0, sh.z + self.s_final)) + d * (L * 0.93)

    def _right_arm_ik(self, Q, delta, head, f, reach, fist, hand_target, fist_target):
        rig = self.rig
        # current FK hand position, blended toward the gesture targets
        fk_hand = head[P + "RightHand"]
        lift = Vector((0, wobble(f, 3.3, 3.0, 0.4), 0))
        tgt = fk_hand.lerp(hand_target + lift, reach)
        if fist == 0:
            tgt = tgt + Vector((-13.0, 0.0, 7.0)) * math.sin(math.pi * reach)
        if fist > 0:
            tgt = tgt.lerp(fist_target, fist)
        pole_reach = Vector((-1.0, -0.5, -0.6))
        pole_fist = Vector((-1.0, -0.7, 0.2))
        pole_rest = Vector((-0.3, -0.2, -1.0))
        pole = pole_rest.lerp(pole_reach, reach).lerp(pole_fist, fist)
        # palm toward the light while reaching; knuckles forward for the fist
        fwd_reach = (hand_target - head[P + "RightArm"]).normalized()
        palm_reach = Vector((0.15, 0.55, 0.82)).normalized()
        fwd_fist = Vector((0.85, 0.35, 0.2)).normalized()
        palm_fist = Vector((0.0, 0.0, -1.0))
        fd = fwd_reach.lerp(fwd_fist, fist).normalized()
        pd = palm_reach.lerp(palm_fist, fist).normalized()
        hand_rest_dir = rig.head0[P + "RightHandMiddle1"] - rig.head0[P + "RightHand"]
        want_hand = frame_rot(hand_rest_dir, Vector((0, -1, 0)), fd, -pd)
        fk_hand_delta = delta[P + "RightHand"]
        w = max(reach, fist)
        end_delta = fk_hand_delta.slerp(want_hand, w)
        rig.two_bone(Q, delta, head, P + "RightArm", P + "RightForeArm", P + "RightHand",
                     tgt, pole, Vector((0, 0, -1)), end_delta=end_delta)
