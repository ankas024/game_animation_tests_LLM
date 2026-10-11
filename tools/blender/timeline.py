"""
Keyframe timeline for rigkit channels.

* every channel is keyed independently: key(frame, ease=None, **channels)
* interpolation is monotone cubic (PCHIP): smooth through intermediate keys,
  flat (ease in/out) on extremes, never overshoots a key
* a key may carry an explicit ease for the segment that *starts* at it
  ('lin', 'in', 'out', 'inout', 'snap', 'outback', 'hold', ...)
* angle channels are unwrapped (closest to the previous key) so spins need
  intermediate keys every < 180 degrees and everything else "just works"
* sword / left-hand frames and hand directions are authored as vectors
  and converted to Euler channels with branch selection for continuity
* per-group time offsets give overlapping action (hips lead, arm/head drag)
"""
import math
from collections import defaultdict
from mathutils import Vector, Matrix

ANGLE_CH = {"root_yaw", "hips_yaw", "hips_pitch", "hips_roll", "hd_yaw", "hd_pitch", "hd_roll",
            "sw_az", "sw_el", "sw_roll", "rh_az", "rh_el", "lh_az", "lh_el",
            "lhd_az", "lhd_el", "lhd_roll", "lf_yaw", "rf_yaw"}

EASES = {
    "lin": lambda u: u,
    "in": lambda u: u * u,
    "in3": lambda u: u * u * u,
    "out": lambda u: 1 - (1 - u) ** 2,
    "out3": lambda u: 1 - (1 - u) ** 3,
    "snap": lambda u: 1 - (1 - u) ** 4,
    "inout": lambda u: u * u * (3 - 2 * u),
    "inout3": lambda u: 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2,
    "outback": lambda u: 1 + 2.2 * (u - 1) ** 3 + 1.2 * (u - 1) ** 2,
    "hold": lambda u: 0.0 if u < 1 else 1.0,
}


def _whip(u):
    # slow start, explosive middle, soft landing: a strike curve
    a = 2.6
    return 1 - (1 - u ** a) ** 3 if u < 1 else 1.0


EASES["whip"] = _whip


def dir_angles(v):
    v = Vector(v).normalized()
    el = math.degrees(math.asin(max(-1, min(1, v.z))))
    az = math.degrees(math.atan2(v.x, v.y))
    return az, el


def frame_angles(y, x):
    """Euler (az, el, roll) for a frame with Y axis y and X axis ~x."""
    y = Vector(y).normalized()
    x = Vector(x)
    x = (x - x.dot(y) * y).normalized()
    el = math.degrees(math.asin(max(-1, min(1, y.z))))
    if abs(y.z) > 0.9995:
        az = None
    else:
        az = math.degrees(math.atan2(y.x, y.y))
    return az, el, x


def _roll_for(az, el, x):
    A = (Matrix.Rotation(math.radians(-az), 3, 'Z') @ Matrix.Rotation(math.radians(el), 3, 'X'))
    loc = A.transposed() @ x
    return math.degrees(math.atan2(-loc.z, loc.x))


def _unwrap(v, ref):
    return v + 360.0 * round((ref - v) / 360.0)


class Timeline:
    def __init__(self, fps=60):
        self.fps = fps
        self.keys = defaultdict(list)       # ch -> [(f, v, ease)]
        self.frames = []                    # (f, kind, data, ease)
        self.offsets = {}                   # ch prefix -> frame offset
        self.layers = []                    # procedural additive fns(f, pose)
        self._final = None

    # ------------------------------------------------------------------
    def key(self, f, ease=None, **ch):
        for k, v in ch.items():
            self.keys[k].append((float(f), float(v), ease))
        self._final = None

    def sword(self, f, blade, edge, ease=None):
        """Key the sword frame from a blade direction and an edge direction."""
        self.frames.append((float(f), "sw", (Vector(blade), Vector(edge)), ease))
        self._final = None

    def lhand(self, f, fingers, thumb, ease=None):
        self.frames.append((float(f), "lhd", (Vector(fingers), Vector(thumb)), ease))
        self._final = None

    def rdir(self, f, d, r=None, ease=None):
        self.frames.append((float(f), "rh", (Vector(d),), ease))
        if r is not None:
            self.key(f, ease, rh_r=r)
        self._final = None

    def ldir(self, f, d, r=None, ease=None):
        self.frames.append((float(f), "lh", (Vector(d),), ease))
        if r is not None:
            self.key(f, ease, lh_r=r)
        self._final = None

    # ------------------------------------------------------------------
    def _resolve_frames(self):
        groups = defaultdict(list)
        for f, kind, data, ease in self.frames:
            groups[kind].append((f, data, ease))
        for kind, items in groups.items():
            items.sort(key=lambda t: t[0])
            prev = None
            for f, data, ease in items:
                if kind in ("sw", "lhd"):
                    y, x = data
                    az, el, xn = frame_angles(y, x)
                    if az is None:
                        az = prev[0] if prev else 0.0
                    cands = []
                    for (a, e) in ((az, el), (az + 180.0, 180.0 - el)):
                        r = _roll_for(a, e, xn)
                        cands.append([a, e, r])
                    if prev:
                        best = None
                        for cnd in cands:
                            cnd = [_unwrap(cnd[i], prev[i]) for i in range(3)]
                            d = sum(abs(cnd[i] - prev[i]) for i in range(3))
                            if best is None or d < best[0]:
                                best = (d, cnd)
                        val = best[1]
                    else:
                        val = cands[0]
                    names = ("sw_az", "sw_el", "sw_roll") if kind == "sw" else \
                            ("lhd_az", "lhd_el", "lhd_roll")
                else:
                    az, el = dir_angles(data[0])
                    cands = [[az, el], [az + 180.0, 180.0 - el]]
                    if prev:
                        best = None
                        for cnd in cands:
                            cnd = [_unwrap(cnd[i], prev[i]) for i in range(2)]
                            d = sum(abs(cnd[i] - prev[i]) for i in range(2))
                            if best is None or d < best[0]:
                                best = (d, cnd)
                        val = best[1]
                    else:
                        val = cands[0]
                    names = ("rh_az", "rh_el") if kind == "rh" else ("lh_az", "lh_el")
                prev = val
                for n, v in zip(names, val):
                    self.keys[n].append((f, v, ease))

    def finalize(self):
        if self._final is not None:
            return self._final
        saved = {k: list(v) for k, v in self.keys.items()}
        self._resolve_frames()
        final = {}
        for ch, ks in self.keys.items():
            ks = sorted(ks, key=lambda t: t[0])
            # drop duplicates (last wins)
            dedup = []
            for k in ks:
                if dedup and abs(dedup[-1][0] - k[0]) < 1e-6:
                    dedup[-1] = k
                else:
                    dedup.append(k)
            ks = dedup
            if ch in ANGLE_CH:
                out = []
                for i, (f, v, e) in enumerate(ks):
                    if out:
                        v = _unwrap(v, out[-1][1])
                    out.append((f, v, e))
                ks = out
            final[ch] = self._prep(ks)
        self.keys = defaultdict(list, saved)
        self._final = final
        return final

    @staticmethod
    def _prep(ks):
        n = len(ks)
        t = [k[0] for k in ks]
        y = [k[1] for k in ks]
        d = [0.0] * n
        if n > 2:
            h = [t[i + 1] - t[i] for i in range(n - 1)]
            dl = [(y[i + 1] - y[i]) / h[i] for i in range(n - 1)]
            for i in range(1, n - 1):
                if dl[i - 1] * dl[i] <= 0:
                    d[i] = 0.0
                else:
                    w1 = 2 * h[i] + h[i - 1]
                    w2 = h[i] + 2 * h[i - 1]
                    d[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])
        # 'cr' keys: Catmull-Rom tangent (keeps speed through pass-through keys,
        # e.g. circular paths and mid-swing keys) and plain Hermite segments
        eases = [k[2] for k in ks]
        for i in range(n):
            if eases[i] == "cr":
                if 0 < i < n - 1:
                    d[i] = (y[i + 1] - y[i - 1]) / (t[i + 1] - t[i - 1])
                eases[i] = None
        return (t, y, d, eases)

    @staticmethod
    def _eval(prep, f):
        t, y, d, e = prep
        n = len(t)
        if f <= t[0]:
            return y[0]
        if f >= t[-1]:
            return y[-1]
        lo, hi = 0, n - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if t[m] <= f:
                lo = m
            else:
                hi = m
        i = lo
        h = t[i + 1] - t[i]
        u = (f - t[i]) / h
        ease = e[i]
        if ease is not None:
            return y[i] + (y[i + 1] - y[i]) * EASES[ease](u)
        h00 = 2 * u ** 3 - 3 * u ** 2 + 1
        h10 = u ** 3 - 2 * u ** 2 + u
        h01 = -2 * u ** 3 + 3 * u ** 2
        h11 = u ** 3 - u ** 2
        return h00 * y[i] + h10 * h * d[i] + h01 * y[i + 1] + h11 * h * d[i + 1]

    def offset_for(self, ch):
        best = 0.0
        blen = -1
        for pre, off in self.offsets.items():
            if ch.startswith(pre) and len(pre) > blen:
                best, blen = off, len(pre)
        return best

    def sample(self, f):
        final = self.finalize()
        pose = {}
        for ch, prep in final.items():
            pose[ch] = self._eval(prep, f - self.offset_for(ch))
        for fn in self.layers:
            fn(f, pose)
        return pose

    def last_frame(self):
        final = self.finalize()
        return max(p[0][-1] for p in final.values())
