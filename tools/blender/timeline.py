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
* optional post-process (`bake_cache`): the sampled channels run through
  damped springs (follow-through / settle on secondary channels) and a
  Gaussian low-pass, so the final curves are smooth to the second derivative
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
        self.tans = defaultdict(dict)       # ch -> {frame: explicit slope (units/frame)}
        # post-process (used once bake_cache() has run)
        self.springs = {}                   # ch prefix -> (omega rad/frame, zeta)
        self.sigma = {}                     # ch prefix -> Gaussian sigma (frames)
        self.default_sigma = 0.0
        self._cache = None
        self._final = None

    # ------------------------------------------------------------------
    def key(self, f, ease=None, **ch):
        for k, v in ch.items():
            self.keys[k].append((float(f), float(v), ease))
        self._final = None

    def tan(self, f, **ch):
        """Explicit tangent (units per frame) for keys at frame f; the
        segments either side must use the default (Hermite) interpolation."""
        for k, v in ch.items():
            self.tans[k][float(f)] = float(v)
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
            final[ch] = self._prep(ks, self.tans.get(ch))
        self.keys = defaultdict(list, saved)
        self._final = final
        return final

    @staticmethod
    def _prep(ks, tans=None):
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
        if tans:
            for i in range(n):
                for tf, sl in tans.items():
                    if abs(tf - t[i]) < 1e-6:
                        d[i] = sl
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

    def raw(self, f):
        final = self.finalize()
        pose = {}
        for ch, prep in final.items():
            pose[ch] = self._eval(prep, f - self.offset_for(ch))
        for fn in self.layers:
            fn(f, pose)
        return pose

    def sample(self, f):
        if self._cache is None:
            return self.raw(f)
        f0, data = self._cache
        n = len(next(iter(data.values())))
        x = min(max(f - f0, 0.0), n - 1.0)
        i = min(int(math.floor(x)), n - 2)
        u = x - i
        ia, ib, ic, idd = max(i - 1, 0), i, i + 1, min(i + 2, n - 1)
        pose = {}
        for ch, arr in data.items():
            p0, p1, p2, p3 = arr[ia], arr[ib], arr[ic], arr[idd]
            # Catmull-Rom between cached frames (sub-frame samples for fx / motion blur)
            pose[ch] = 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u)
        return pose

    def _param(self, table, ch, default):
        best, blen = default, -1
        for pre, val in table.items():
            if ch.startswith(pre) and len(pre) > blen:
                best, blen = val, len(pre)
        return best

    def bake_cache(self, f0=None, f1=None, pad=24):
        """Sample every frame once, then run springs + low-pass per channel.
        After this, sample() reads the processed curves."""
        self._cache = None
        f0 = 0 if f0 is None else f0
        f1 = self.end if f1 is None else f1
        a, b = int(f0) - pad, int(f1) + pad
        frames = list(range(a, b + 1))
        raws = [self.raw(f) for f in frames]
        data = {}
        for ch in raws[0]:
            x = [r[ch] for r in raws]
            sp = self._param(self.springs, ch, None)
            if sp:
                x = self._spring(x, *sp)
            sg = self._param(self.sigma, ch, self.default_sigma)
            if sg and sg > 0:
                x = self._gauss(x, sg)
            data[ch] = x
        # trim the padding
        data = {ch: arr[pad:len(arr) - pad] for ch, arr in data.items()}
        self._cache = (int(f0), data)

    @staticmethod
    def _spring(x, omega, zeta, sub=8):
        """Damped spring follower.  The input is read ahead by the spring's
        ramp lag (2 zeta / omega) so poses still land on time; what remains
        is the overshoot / settle and the rounding of sharp changes."""
        lag = 2.0 * zeta / omega
        n = len(x)

        def xin(t):
            t = min(max(t, 0.0), n - 1.0)
            i = min(int(t), n - 2)
            u = t - i
            return x[i] * (1 - u) + x[i + 1] * u
        y, v = xin(lag), 0.0
        out = []
        dt = 1.0 / sub
        for f in range(n):
            out.append(y)
            for s in range(sub):
                tgt = xin(f + lag + s * dt)
                acc = omega * omega * (tgt - y) - 2.0 * zeta * omega * v
                v += acc * dt
                y += v * dt
        return out

    @staticmethod
    def _gauss(x, sigma):
        r = int(math.ceil(sigma * 3))
        w = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-r, r + 1)]
        ws = sum(w)
        n = len(x)
        out = []
        for i in range(n):
            acc = 0.0
            for k in range(-r, r + 1):
                acc += w[k + r] * x[min(max(i + k, 0), n - 1)]
            out.append(acc / ws)
        return out

    def last_frame(self):
        final = self.finalize()
        return max(p[0][-1] for p in final.values())
