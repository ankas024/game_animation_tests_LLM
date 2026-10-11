"""
Preview-render FX: sword trail ribbons, summon / dismiss shards, impact ring.
All geometry is rebuilt per frame from the timeline (sub-frame sampled),
so it can be driven from a simple render loop.
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector, Matrix

import rigkit

BLADE_BASE = 0.075
BLADE_TIP = 0.775


def _smooth(a, b, x):
    if b == a:
        return 1.0 if x >= b else 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


class SwordSampler:
    """Caches world-space sword samples at fractional frames."""

    def __init__(self, rig, T):
        self.rig, self.T = rig, T
        self.cache = {}

    def at(self, t):
        key = round(t * 8) / 8
        if key in self.cache:
            return self.cache[key]
        c = self.T.sample(key)
        R, H, G = self.rig.solve(c)
        Wr, Wp = self.rig.to_world(c, R, H)
        M = Wr[rigkit.WEAPON].to_4x4()
        M.translation = Wp[rigkit.WEAPON]
        res = dict(M=M, mat=c["sw_mat"], hips=Wp[rigkit.P + "Hips"].copy(),
                   head=Wp[rigkit.P + "Head"].copy())
        self.cache[key] = res
        return res

    def point(self, t, y, x=0.0):
        s = self.at(t)
        return s["M"] @ Vector((x, y, 0.0))


# ---------------------------------------------------------------------------
def _mesh_obj(name, mat):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    return ob


def _replace_mesh(ob, bm):
    me = ob.data
    bm.to_mesh(me)
    me.update()
    bm.free()


class Trail:
    def __init__(self, sampler, mat, length=4.0, step=0.25):
        self.s = sampler
        self.ob = _mesh_obj("FX_Trail", mat)
        self.length, self.step = length, step

    def update(self, f):
        bm = bmesh.new()
        col = bm.loops.layers.color.new("fx")
        n = int(self.length / self.step)
        rows = []
        for k in range(n + 1):
            t = f - k * self.step
            s = self.s.at(t)
            if s["mat"] < 0.05:
                break
            tip = self.s.point(t, BLADE_TIP + 0.02)
            tip_prev = self.s.point(t - 0.5, BLADE_TIP + 0.02)
            speed = (tip - tip_prev).length * 120.0          # m/s
            inner = self.s.point(t, BLADE_BASE + 0.32)
            mid = self.s.point(t, BLADE_BASE + 0.56)
            a = (k / n)
            w = _smooth(5.0, 16.0, speed) * min(1.0, s["mat"] * 1.5)
            rows.append(([inner, mid, tip], a, w))
        if len(rows) >= 2:
            verts = [[bm.verts.new(p) for p in r[0]] for r in rows]
            across = (0.0, 0.55, 1.0)
            for i in range(len(rows) - 1):
                for j in range(2):
                    q = (verts[i][j], verts[i][j + 1], verts[i + 1][j + 1], verts[i + 1][j])
                    try:
                        face = bm.faces.new(q)
                    except ValueError:
                        continue
                    for loop in face.loops:
                        ri = i if loop.vert in verts[i] else i + 1
                        cj = verts[ri].index(loop.vert)
                        age, wgt = rows[ri][1], rows[ri][2]
                        loop[col] = (age, across[cj], wgt, 1.0)
        _replace_mesh(self.ob, bm)


class Shards:
    """Summon: shards converge on the blade (hilt first).  Dismiss: blade
    breaks into shards from tip to hilt that drift up and fade."""

    def __init__(self, sampler, mat, summon=(36, 58), dismiss=(302, 330), impact=None, n=220, seed=7):
        self.s = sampler
        self.ob = _mesh_obj("FX_Shards", mat)
        rnd = random.Random(seed)
        self.summon, self.dismiss, self.impact = summon, dismiss, impact
        self.items = []
        for i in range(n):
            u = rnd.random()
            d = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
            self.items.append(dict(
                u=u, x=rnd.uniform(-0.012, 0.016), d=d, r=rnd.uniform(0.18, 0.62),
                size=rnd.uniform(0.006, 0.016), spin=Vector((rnd.random(), rnd.random(), rnd.random())),
                jit=rnd.uniform(-3.0, 3.0), up=rnd.uniform(0.2, 1.0), drift=rnd.uniform(0.6, 1.4)))
        self.debris = []
        for i in range(90):
            a = rnd.uniform(0, 2 * math.pi)
            self.debris.append(dict(a=a, v=rnd.uniform(1.2, 3.6), vz=rnd.uniform(1.0, 3.2),
                                    size=rnd.uniform(0.008, 0.02), spin=Vector((rnd.random(), rnd.random(), rnd.random())),
                                    delay=rnd.uniform(0, 2.5)))

    def _tri(self, bm, col, p, size, spin, t, glow, tint):
        R = (Matrix.Rotation(spin.x * 9 + t * 0.4, 3, 'X') @ Matrix.Rotation(spin.y * 9 + t * 0.3, 3, 'Y') @
             Matrix.Rotation(spin.z * 9, 3, 'Z'))
        a = p + R @ Vector((0, size * 1.8, 0))
        b = p + R @ Vector((size * 0.6, -size * 0.6, 0))
        c = p + R @ Vector((-size * 0.6, -size * 0.6, size * 0.3))
        v = [bm.verts.new(x) for x in (a, b, c)]
        face = bm.faces.new(v)
        for loop in face.loops:
            loop[col] = (glow, tint, 1.0, 1.0)

    def update(self, f):
        bm = bmesh.new()
        col = bm.loops.layers.color.new("fx")
        s0, s1 = self.summon
        if s0 - 14 <= f <= s1 + 4:
            for it in self.items:
                arrive = s0 + 6 + (s1 - s0 - 6) * it["u"] + it["jit"] * 0.5
                start = arrive - 13
                if not (start <= f <= arrive + 2):
                    continue
                k = _smooth(start, arrive, f)
                anchor = self.s.point(f, BLADE_BASE + (BLADE_TIP - BLADE_BASE) * it["u"], it["x"])
                off = it["d"] * it["r"] * (1 - k) ** 1.6
                swirl = Matrix.Rotation((1 - k) * 2.5, 3, it["d"].orthogonal().normalized())
                p = anchor + swirl @ off
                glow = 0.4 + 0.6 * k
                if f > arrive:
                    glow *= max(0.0, 1 - (f - arrive) / 2.0)
                self._tri(bm, col, p, it["size"] * (1.4 - 0.6 * k), it["spin"], f, glow, 0.0)
        d0, d1 = self.dismiss
        if d0 <= f <= d1 + 26:
            for it in self.items:
                depart = d0 + (d1 - d0) * (1 - it["u"]) * 0.85 + it["jit"] * 0.4
                if f < depart:
                    continue
                age = f - depart
                if age > 26:
                    continue
                anchor = self.s.point(min(depart, f), BLADE_BASE + (BLADE_TIP - BLADE_BASE) * it["u"], it["x"])
                vel = it["d"] * 0.35 * it["drift"] + Vector((0, 0, 0.55 * it["up"]))
                tt = age / 60.0
                p = anchor + vel * (1 - math.exp(-tt * 3.0)) / 3.0 * 2.2 + Vector((0, 0, 0.25 * tt * tt))
                glow = (1 - age / 26.0) ** 1.3
                self._tri(bm, col, p, it["size"] * (1.0 - 0.5 * age / 26.0), it["spin"], f, glow, 0.0)
        if self.impact:
            fi, centre = self.impact
            if fi <= f <= fi + 40:
                for it in self.debris:
                    age = (f - fi - it["delay"]) / 60.0
                    if age < 0:
                        continue
                    dirv = Vector((math.cos(it["a"]), math.sin(it["a"]), 0))
                    p = centre + dirv * it["v"] * age * 0.6 + Vector((0, 0, it["vz"] * age - 4.9 * age * age))
                    if p.z < 0:
                        continue
                    glow = max(0.0, 1 - age / 0.42) * 0.8
                    self._tri(bm, col, p, it["size"], it["spin"], f, glow, 1.0)
        _replace_mesh(self.ob, bm)


class ImpactRing:
    def __init__(self, mat, frame, centre):
        self.frame, self.centre = frame, centre
        self.ob = _mesh_obj("FX_Ring", mat)
        bm = bmesh.new()
        col = bm.loops.layers.color.new("fx")
        n = 96
        inner = [bm.verts.new((math.cos(2 * math.pi * i / n) * 0.90, math.sin(2 * math.pi * i / n) * 0.90, 0))
                 for i in range(n)]
        outer = [bm.verts.new((math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0)) for i in range(n)]
        for i in range(n):
            face = bm.faces.new((inner[i], inner[(i + 1) % n], outer[(i + 1) % n], outer[i]))
            for loop in face.loops:
                loop[col] = (0.0, 1.0 if loop.vert in outer else 0.0, 1.0, 1.0)
        bm.to_mesh(self.ob.data)
        bm.free()
        self.ob.location = centre + Vector((0, 0, 0.004))

    def update(self, f):
        age = f - self.frame
        if age < 0 or age > 30:
            self.ob.hide_render = True
            return
        self.ob.hide_render = False
        r = 0.12 + 1.25 * (1 - math.exp(-age / 6.0))
        self.ob.scale = (r, r, 1)
        self.ob["fade"] = 0.6 * max(0.0, 1 - age / 26.0) ** 2
