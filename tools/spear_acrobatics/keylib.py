"""Small helpers for writing keys."""
from rig import SPEAR_LEN

HALF = SPEAR_LEN / 2   # blade tip at +HALF, butt at -HALF along the shaft


def planted(side, x, y, yaw=0.0, pit=0.0, z=0.0, ko=0.0, rol=0.0):
    p = side + "l_"
    return {p + "w": 1.0, p + "bx": x, p + "by": y, p + "bz": z, p + "yaw": yaw, p + "pit": pit,
            p + "ko": ko, p + "rol": rol}


def fk_leg(side, fl, kn, ab=3.0, ex=0.0, an=0.0):
    p = side + "l_"
    return {p + "w": 0.0, p + "fl": fl, p + "kn": kn, p + "ab": ab, p + "ex": ex, p + "an": an}


def arm(side, az, el, d=0.95, sw=0.0, curl=None, wf=0.0, wd=0.0, wt=0.0):
    p = side + "a_"
    out = {p + "az": az, p + "el": el, p + "d": d, p + "sw": sw, p + "wf": wf, p + "wd": wd, p + "wt": wt}
    if curl is not None:
        out[p + "curl"] = curl
    return out


def grip(side, s, g=1.0, h=1.0, gr=0.0):
    p = side + "a_"
    return {p + "h": h, p + "s": s, p + "g": g, p + "gr": gr}


def free(side):
    return {side + "a_h": 0.0}


def spear_world(x, y, z, ang, dep=0.0, sa=0.0, roll=0.0, k=0.0, kd=0.0, at=0.0, kp=0.0):
    return dict(sx=x, sy=y, sz=z, sang=ang, sdep=dep, sa=sa, sroll=roll, sk=k, skd=kd, skp=kp, sat=at,
                scr=0.0, scl=0.0)


def spear_carry(side, ang, dep=0.0, roll=0.0, k=0.0):
    d = dict(sang=ang, sdep=dep, sroll=roll, sk=k, scr=0.0, scl=0.0)
    d["scr" if side == "r" else "scl"] = 1.0
    return d


def body(x, y, z, yaw=0.0, pitch=0.0, roll=0.0, sb=0.0, ss=0.0, st=0.0, nb=0.0, ns=0.0, nt=0.0, twist=0.0):
    return dict(hx=x, hy=y, hz=z, yaw=yaw, pitch=pitch, roll=roll, twist=twist,
                sb=sb, ss=ss, st=st, nb=nb, ns=ns, nt=nt)


def K(tl, f, *parts):
    d = {}
    for p in parts:
        d.update(p)
    tl.key(f, **d)


