"""
Numeric sanity checks over the whole combo (no rendering).

    python -I diag.py [first last]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,F401
from mathutils import Vector  # noqa: E402
import scene_util as su  # noqa: E402
import rigkit  # noqa: E402
import combo  # noqa: E402
from rigkit import P  # noqa: E402

BLADE_TIP = 0.777


def main():
    arm, meshes = su.load_character()
    rig = rigkit.Rig(arm)
    rig.ensure_weapon_bone()
    T = combo.build(rig)
    a, b = (int(sys.argv[-2]), int(sys.argv[-1])) if len(sys.argv) > 2 else (0, T.end)
    prev = None
    issues = []
    for f in range(a, b + 1):
        c = T.sample(f)
        R, H, G = rig.solve(c)
        Wr, Wp = rig.to_world(c, R, H)
        rec = {}
        # sword tip
        if c["sw_mat"] > 0.01:
            tip = Wp[rigkit.WEAPON] + Wr[rigkit.WEAPON] @ Vector((0, BLADE_TIP, 0))
            pom = Wp[rigkit.WEAPON] + Wr[rigkit.WEAPON] @ Vector((0, -0.135, 0))
            rec["tip"] = tip
            if min(tip.z, pom.z) < 0.015:
                issues.append((f, "sword below floor", round(min(tip.z, pom.z), 3)))
            # blade through torso: distance from spine2/hips line to blade segment
            base = Wp[rigkit.WEAPON] + Wr[rigkit.WEAPON] @ Vector((0, 0.07, 0))
            for bn, rad in (("Spine1", 0.085), ("Hips", 0.10), ("Head", 0.08), ("Spine2", 0.09)):
                pt = Wp[P + bn] + Vector((0, 0, 0.03))
                d = seg_dist(pt, base, tip)
                if d < rad:
                    issues.append((f, f"blade near {bn}", round(d, 3)))
            fa0, fa1 = Wp[P + "RightForeArm"], Wp[P + "RightHand"]
            d = seg_seg(base, tip, fa0 + (fa1 - fa0) * 0.05, fa0 + (fa1 - fa0) * 0.8)
            if d < 0.032:
                issues.append((f, "blade through right forearm", round(d, 3)))
            for bn in ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"):
                p0 = Wp[P + bn]
                child = {"LeftUpLeg": "LeftLeg", "RightUpLeg": "RightLeg",
                         "LeftLeg": "LeftFoot", "RightLeg": "RightFoot"}[bn]
                p1 = Wp[P + child]
                d = seg_seg(base, tip, p0, p1)
                if d < 0.055:
                    issues.append((f, f"blade through {bn}", round(d, 3)))
        # feet
        for s, k in (("Left", "lf"), ("Right", "rf")):
            ball = Wp[P + s + "ToeBase"]
            rec[s] = ball
            if prev and c[k + "_z"] < 0.003 and prev["c"][k + "_z"] < 0.003 and c[k + "_space"] < 0.01:
                dv = (ball - prev[s]).copy()
                dv.z = 0
                if dv.length > 0.004:
                    issues.append((f, f"{s} foot slide", round(dv.length, 4)))
            # ik reach: ankle position vs desired
            ank = Wp[P + s + "Foot"]
            if ank.z < 0.02:
                issues.append((f, f"{s} ankle low", round(ank.z, 3)))
            knee = Wp[P + s + "Leg"]
            if knee.z < 0.04:
                issues.append((f, f"{s} knee in floor", round(knee.z, 3)))
            toe_end = Wp[P + s + "Toe_End"]
            if toe_end.z < -0.01:
                issues.append((f, f"{s} toe below floor", round(toe_end.z, 3)))
            hip = Wp[P + s + "UpLeg"]
            reach = (hip - ank).length / (rig.len[s + "Thigh"] + rig.len[s + "Shin"])
            if reach > 0.995:
                issues.append((f, f"{s} leg straight/overreach", round(reach, 4)))
        # wrists
        for s in ("Left", "Right"):
            fa = Wr[P + s + "ForeArm"] @ Vector((0, 1, 0))
            hy = Wr[P + s + "Hand"] @ Vector((0, 1, 0))
            bend = math.degrees(fa.angle(hy))
            rel = (Wr[P + s + "ForeArm"].transposed() @ Wr[P + s + "Hand"]).to_quaternion()
            tw = math.degrees(2 * math.atan2(rel.y, rel.w))
            tw = (tw + 180) % 360 - 180
            if bend > 75:
                issues.append((f, f"{s} wrist bend", round(bend)))
            if abs(tw) > 70:
                issues.append((f, f"{s} wrist twist", round(tw)))
            sh = Wp[P + s + "Arm"]
            wr = Wp[P + s + "Hand"]
            arm_reach = (wr - sh).length / (rig.len[s + "Arm"] + rig.len[s + "Fore"])
            if arm_reach > 0.999:
                issues.append((f, f"{s} arm overreach", round(arm_reach, 4)))
            # elbow bending backwards: hinge sign check
            el = Wp[P + s + "ForeArm"]
            ua = (el - sh).normalized()
            fo = (wr - el).normalized()
            if ua.angle(fo) > math.radians(150):
                issues.append((f, f"{s} elbow hyper", round(math.degrees(ua.angle(fo)))))
        for bn in ("Hips", "Head", "LeftHand", "RightHand"):
            if Wp[P + bn].z < 0.03:
                issues.append((f, f"{bn} below floor", round(Wp[P + bn].z, 3)))
        prev = dict(rec, c=c)
    # compress consecutive duplicates
    last = {}
    for f, what, val in issues:
        key = what
        if key in last and last[key][1] == f - 1:
            last[key][1] = f
            last[key][2] = min(last[key][2], val) if isinstance(val, float) else val
            continue
        if key in last:
            print_issue(last[key], key)
        last[key] = [f, f, val]
    for key, v in last.items():
        print_issue(v, key)


def print_issue(v, key):
    print(f"  f{v[0]}-{v[1]}: {key} ({v[2]})")


def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def seg_seg(p1, q1, p2, q2):
    best = 1e9
    for i in range(11):
        t = i / 10
        best = min(best, seg_dist(p1 + (q1 - p1) * t, p2, q2))
    return best


main()
