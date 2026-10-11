"""Per-channel keyframe timeline.

Every channel is keyed independently (a key only lists the channels it sets).
Interpolation is monotone cubic (Fritsch-Carlson / PCHIP): smooth through
intermediate keys, flat on extremes and plateaus, never overshoots. Planted
feet stay planted, and angles that only go one way (a flip) stay monotone.
Stepped channels (grip thumb direction) hold the previous key's value.
The spear's screen angle is unwrapped key to key (shortest turn), so keys can
be written as plain -180..180 readings off the reference.
Optional Gaussian smoothing per channel runs after sampling.
"""
import math
from collections import defaultdict

from rig import DEFAULTS

STEPPED = {"la_g", "ra_g"}
# angle channels unwrapped to the shortest turn from the previous key
UNWRAP = {"sang"}


def pchip_slopes(t, v):
    n = len(t)
    if n < 2:
        return [0.0] * n
    h = [t[i + 1] - t[i] for i in range(n - 1)]
    d = [(v[i + 1] - v[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    # end slopes: one-sided three-point estimate, clipped (Fritsch-Carlson)
    if n > 2:
        m[0] = _end_slope(h[0], h[1], d[0], d[1])
        m[-1] = _end_slope(h[-1], h[-2], d[-1], d[-2])
    return m


def _end_slope(h0, h1, d0, d1):
    m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if m * d0 <= 0:
        return 0.0
    if d0 * d1 <= 0 and abs(m) > abs(3 * d0):
        return 3 * d0
    return m


class Timeline:
    def __init__(self, f0, f1):
        self.f0, self.f1 = f0, f1
        self.keys = defaultdict(dict)   # ch -> {frame: value}
        self.slope = defaultdict(dict)  # ch -> {frame: explicit slope}
        self.sigma = {}                 # ch -> gaussian sigma (frames)
        self.default_sigma = 0.0
        self._cache = None

    def key(self, f, **ch):
        for k, v in ch.items():
            if k not in DEFAULTS:
                raise KeyError(f"unknown channel {k} at frame {f}")
            self.keys[k][float(f)] = float(v)
        self._cache = None

    def pose(self, f, d):
        self.key(f, **d)

    def tangent(self, f, **ch):
        for k, v in ch.items():
            self.slope[k][float(f)] = float(v)
        self._cache = None

    # ------------------------------------------------------------------
    def _sample_channel(self, ch, frames):
        kd = self.keys.get(ch)
        if not kd:
            return [DEFAULTS[ch]] * len(frames)
        ts = sorted(kd)
        vs = [kd[t] for t in ts]
        if ch in UNWRAP:
            for i in range(1, len(vs)):
                vs[i] += 360.0 * round((vs[i - 1] - vs[i]) / 360.0)
        if ch in STEPPED:
            out = []
            for f in frames:
                v = vs[0]
                for t, x in zip(ts, vs):
                    if t <= f:
                        v = x
                out.append(v)
            return out
        ms = pchip_slopes(ts, vs)
        for i, t in enumerate(ts):
            if t in self.slope.get(ch, {}):
                ms[i] = self.slope[ch][t]
        out = []
        j = 0
        for f in frames:
            if f <= ts[0]:
                out.append(vs[0])
                continue
            if f >= ts[-1]:
                out.append(vs[-1])
                continue
            while ts[j + 1] < f:
                j += 1
            h = ts[j + 1] - ts[j]
            u = (f - ts[j]) / h
            h00 = 2 * u ** 3 - 3 * u ** 2 + 1
            h10 = u ** 3 - 2 * u ** 2 + u
            h01 = -2 * u ** 3 + 3 * u ** 2
            h11 = u ** 3 - u ** 2
            out.append(h00 * vs[j] + h10 * h * ms[j] + h01 * vs[j + 1] + h11 * h * ms[j + 1])
        return out

    @staticmethod
    def _gauss(vals, sigma):
        if sigma <= 0:
            return list(vals)
        r = int(math.ceil(sigma * 3))
        w = [math.exp(-0.5 * (i / sigma) ** 2) for i in range(-r, r + 1)]
        n = len(vals)
        out = []
        for i in range(n):
            acc = ws = 0.0
            for k, wk in enumerate(w):
                j = min(max(i + k - r, 0), n - 1)
                acc += vals[j] * wk
                ws += wk
            out.append(acc / ws)
        return out

    def bake(self):
        frames = list(range(self.f0, self.f1 + 1))
        data = {}
        for ch in DEFAULTS:
            vals = self._sample_channel(ch, frames)
            sg = self.sigma.get(ch, self.default_sigma)
            data[ch] = self._gauss(vals, sg) if sg else vals
        self._cache = (frames, data)
        return self._cache

    def at(self, f):
        if self._cache is None:
            self.bake()
        frames, data = self._cache
        i = min(max(int(round(f)) - self.f0, 0), len(frames) - 1)
        return {ch: arr[i] for ch, arr in data.items()}
