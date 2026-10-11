"""Procedural ruined gothic cathedral for VIGIL.

World layout (metres): the nave runs along +Y, from the west door (y=-21)
to the rose window wall (y=+24). Pier centres sit at x=+-5, every 4 m.
A collapsed section of the vault lets a shaft of moonlight onto the aisle.
"""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

import materials as M

NAVE_X = 5.0
WALL_T = 0.9
AISLE_X = 9.5
Y_WEST = -21.0
Y_EAST = 24.0
PIER_YS = [-17.0 + 4.0 * k for k in range(10)]
ARCADE_SPRING = 7.0
CLERESTORY_BASE = 10.5
VAULT_SPRING = 16.5
AISLE_H = 10.0
SANCTUARY_Y = 16.5


# --------------------------------------------------------------------------- mesh utils

def link(obj, col):
    col.objects.link(obj)
    return obj


def mesh_obj(name, bm, col, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = smooth
    return link(bpy.data.objects.new(name, me), col)


def pointed_arch(u0, u1, v_spring, sharp=0.9, n=24):
    """Points of a pointed (two-centred) arch from left spring to right spring."""
    a = (u1 - u0) / 2.0
    mid = (u0 + u1) / 2.0
    r = max(a * 1.001, 2 * a * sharp)
    off = r - a
    h = math.sqrt(r * r - off * off)
    th1 = math.acos(-off / r)
    pts = []
    for i in range(n + 1):            # left arc, centred right of the midline
        th = math.pi + (th1 - math.pi) * i / n
        pts.append((mid + off + r * math.cos(th), v_spring + r * math.sin(th)))
    for i in range(1, n + 1):         # right arc, centred left of the midline
        th = (math.pi - th1) * (1 - i / n)
        pts.append((mid - off + r * math.cos(th), v_spring + r * math.sin(th)))
    return pts, v_spring + h


def slab(name, col, mat, outer, holes, frame, thickness):
    """Extrude a 2D polygon with holes. ``frame(u, v, w)`` maps to world space."""
    bm = bmesh.new()
    loops2d = [outer] + holes
    front_edges, back_edges, rings = [], [], []
    for pts in loops2d:
        fv = [bm.verts.new(frame(u, v, 0.0)) for u, v in pts]
        bv = [bm.verts.new(frame(u, v, thickness)) for u, v in pts]
        n = len(pts)
        front_edges += [bm.edges.new((fv[i], fv[(i + 1) % n])) for i in range(n)]
        back_edges += [bm.edges.new((bv[i], bv[(i + 1) % n])) for i in range(n)]
        rings.append((fv, bv))
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=front_edges)
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=back_edges)
    for fv, bv in rings:
        n = len(fv)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((fv[i], fv[j], bv[j], bv[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm, col, mat)


def box(name, col, mat, size, loc, rot=(0, 0, 0), bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
    o = mesh_obj(name, bm, col, mat)
    o.location = loc
    o.rotation_euler = rot
    return o


def cylinder(bm, r, h, z0=0.0, segs=16, r_top=None, x=0.0, y=0.0):
    r_top = r if r_top is None else r_top
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r_top, depth=h)
    bmesh.ops.translate(bm, vec=(x, y, z0 + h / 2), verts=res["verts"])


def curve_obj(name, col, mat, pts, bevel, closed=False, res=4):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = res
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (c[0], c[1], c[2], 1)
    sp.use_cyclic_u = closed
    cu.materials.append(mat)
    return link(bpy.data.objects.new(name, cu), col)


def rock(bm, size, seed, loc, rot):
    rnd = random.Random(seed)
    res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    vs = res["verts"]
    sx, sy, sz = size
    for v in vs:
        k = 1.0 + rnd.uniform(-0.18, 0.18)
        v.co = Vector((v.co.x * sx * k, v.co.y * sy * k, v.co.z * sz * k))
    # chunky, flattened facets read as broken masonry
    for v in vs:
        v.co.x = max(-sx * 0.42, min(sx * 0.42, v.co.x))
        v.co.y = max(-sy * 0.42, min(sy * 0.42, v.co.y))
        v.co.z = max(-sz * 0.4, min(sz * 0.4, v.co.z))
    m = Matrix.LocRotScale(Vector(loc), Euler(rot).to_quaternion(), Vector((1, 1, 1)))
    bmesh.ops.transform(bm, matrix=m, verts=vs)


# --------------------------------------------------------------------------- builders

class Cathedral:
    def __init__(self, info):
        """info: dict with 'stop_y', 'hole' (Vector on the vault), 'candle_spots'."""
        self.info = info
        self.col = bpy.data.collections.new("SET")
        bpy.context.scene.collection.children.link(self.col)
        self.rnd = random.Random(7)
        self.m_stone = M.stone()
        self.m_stone_rough = M.stone("M_stone_rough", blocks=False, scale=2.0)
        self.m_rubble = M.stone("M_rubble", tint=(0.62, 0.6, 0.58), blocks=False, scale=3.0)
        self.m_floor = M.floor()
        self.m_wood = M.wood()
        self.m_iron = M.iron()
        self.m_wax = M.wax()
        self.m_flame = M.flame()
        self.m_banner = M.banner()

    def build(self):
        self.floor()
        self.piers()
        self.arcades()
        self.clerestory()
        self.aisle_walls()
        self.end_walls()
        self.vault()
        self.sanctuary()
        self.rose_window()
        self.doors()
        self.pews()
        self.rubble()
        self.banners()
        self.candles()
        self.fog()
        self.motes()
        return self

    # ---- floor
    def floor(self):
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, vec=(2 * AISLE_X + 2, Y_EAST - Y_WEST + 2, 1), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, (Y_EAST + Y_WEST) / 2, 0), verts=bm.verts)
        mesh_obj("floor", bm, self.col, self.m_floor)
        # outside: flagstones continuing into the mist
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, vec=(80, 60, 1), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, Y_WEST - 1.4 - 30, 0), verts=bm.verts)
        mesh_obj("ground_out", bm, self.col, self.m_floor)

    # ---- clustered piers
    def _pier_mesh(self):
        if "pier" in bpy.data.meshes:
            return bpy.data.meshes["pier"]
        bm = bmesh.new()
        cylinder(bm, 0.78, 0.35, 0.0, segs=8)                          # plinth
        cylinder(bm, 0.66, 0.25, 0.35, segs=8, r_top=0.56)             # base moulding
        cylinder(bm, 0.48, ARCADE_SPRING - 0.6, 0.6, segs=20)          # core
        for k in range(8):
            a = k * math.pi / 4 + math.pi / 8
            cylinder(bm, 0.13, ARCADE_SPRING - 0.6, 0.6, segs=10,
                     x=0.5 * math.cos(a), y=0.5 * math.sin(a))
        cylinder(bm, 0.58, 0.5, ARCADE_SPRING - 0.55, segs=16, r_top=0.82)  # capital bell
        cylinder(bm, 0.86, 0.14, ARCADE_SPRING - 0.06, segs=8)         # abacus
        me = bpy.data.meshes.new("pier")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(self.m_stone)
        return me

    def piers(self):
        me = self._pier_mesh()
        for side in (-1, 1):
            for y in PIER_YS:
                o = link(bpy.data.objects.new(f"pier_{side}_{y}", me), self.col)
                o.location = (side * NAVE_X, y, 0)
                # wall shaft running from the capital to the vault springing
                bm = bmesh.new()
                cylinder(bm, 0.16, VAULT_SPRING - ARCADE_SPRING, ARCADE_SPRING + 0.08, segs=10,
                         x=side * (NAVE_X - WALL_T / 2 - 0.12), y=y)
                cylinder(bm, 0.3, 0.3, VAULT_SPRING - 0.3, segs=8, r_top=0.36,
                         x=side * (NAVE_X - WALL_T / 2 - 0.12), y=y)
                mesh_obj(f"shaft_{side}_{y}", bm, self.col, self.m_stone, smooth=True)

    # ---- arcade (pointed arches between piers) + spandrel wall
    def arcades(self):
        ys = [Y_WEST] + PIER_YS + [Y_EAST]
        for side in (-1, 1):
            x0 = side * NAVE_X - WALL_T / 2

            def frame(u, v, w, x0=x0):
                return Vector((x0 + w, u, v))

            for y0, y1 in zip(ys, ys[1:]):
                o0 = y0 + (0.45 if y0 != Y_WEST else 0.6)
                o1 = y1 - (0.45 if y1 != Y_EAST else 0.6)
                arch, peak = pointed_arch(o0, o1, ARCADE_SPRING, sharp=0.85, n=14)
                # U-shaped outline: the opening reaches the floor, so no hole needed
                outer = [(y0, 0.0), (o0, 0.0)] + arch + [(o1, 0.0), (y1, 0.0),
                                                        (y1, CLERESTORY_BASE), (y0, CLERESTORY_BASE)]
                slab(f"arcade_{side}_{y0}", self.col, self.m_stone, outer, [], frame, WALL_T)
                # arch moulding on the nave face
                xf = side * (NAVE_X - WALL_T / 2 - 0.03)
                pts = [(xf, u, v) for u, v in arch]
                curve_obj(f"archmould_{side}_{y0}", self.col, self.m_stone, pts, 0.11)
            curve_obj(f"course_{side}", self.col, self.m_stone,
                      [(side * (NAVE_X - WALL_T / 2 - 0.05), Y_WEST, CLERESTORY_BASE),
                       (side * (NAVE_X - WALL_T / 2 - 0.05), Y_EAST, CLERESTORY_BASE)], 0.13)

    def _wall_with_windows(self, name, frame, u_bounds, v0, v1, windows, thickness, mat):
        holes = []
        for (wu0, wu1, sill, spring, sharp) in windows:
            arch, _ = pointed_arch(wu0, wu1, spring, sharp=sharp, n=10)
            holes.append([(wu0, sill), (wu1, sill)] + list(reversed(arch)))
        outer = [(u_bounds[0], v0), (u_bounds[1], v0), (u_bounds[1], v1), (u_bounds[0], v1)]
        return slab(name, self.col, mat, outer, holes, frame, thickness)

    def clerestory(self):
        ys = [Y_WEST] + PIER_YS + [Y_EAST]
        for side in (-1, 1):
            x0 = side * NAVE_X - WALL_T / 2

            def frame(u, v, w, x0=x0):
                return Vector((x0 + w, u, v))

            wins = []
            for y0, y1 in zip(ys, ys[1:]):
                mid = (y0 + y1) / 2
                wins.append((mid - 0.85, mid + 0.85, 11.2, 14.2, 0.9))
            self._wall_with_windows(f"clerestory_{side}", frame, (Y_WEST, Y_EAST), CLERESTORY_BASE,
                                    VAULT_SPRING + 0.4, wins, WALL_T, self.m_stone)
            # mullion in each window
            for (wu0, wu1, sill, spring, _) in wins:
                um = (wu0 + wu1) / 2
                curve_obj("mullion", self.col, self.m_stone,
                          [(side * NAVE_X, um, sill), (side * NAVE_X, um, spring + 0.9)], 0.07)

    def aisle_walls(self):
        ys = [Y_WEST] + PIER_YS + [Y_EAST]
        for side in (-1, 1):
            x0 = side * AISLE_X if side > 0 else -AISLE_X - WALL_T

            def frame(u, v, w, x0=x0):
                return Vector((x0 + w, u, v))

            wins = []
            for y0, y1 in zip(ys, ys[1:]):
                mid = (y0 + y1) / 2
                wins.append((mid - 0.95, mid + 0.95, 1.9, 6.3, 0.95))
            self._wall_with_windows(f"aislewall_{side}", frame, (Y_WEST, Y_EAST), 0.0, AISLE_H + 0.6,
                                    wins, WALL_T, self.m_stone)
            for (wu0, wu1, sill, spring, _) in wins:
                um = (wu0 + wu1) / 2
                xw = side * (AISLE_X + WALL_T / 2)
                curve_obj("aisle_mullion", self.col, self.m_iron,
                          [(xw, um, sill), (xw, um, spring + 1.0)], 0.03)
                for zb in (2.9, 3.9, 4.9, 5.9):
                    curve_obj("aisle_bar", self.col, self.m_iron,
                              [(xw, wu0, zb), (xw, wu1, zb)], 0.018)
            # aisle ceiling
            xa, xb = sorted((side * (NAVE_X + WALL_T / 2), side * (AISLE_X + WALL_T)))
            box(f"aisle_roof_{side}", self.col, self.m_stone_rough, (xb - xa, Y_EAST - Y_WEST, 0.4),
                ((xa + xb) / 2, (Y_EAST + Y_WEST) / 2, AISLE_H + 0.2))

    def end_walls(self):
        # west wall with the great door and an oculus
        def frame_w(u, v, w):
            return Vector((u, Y_WEST - w, v))

        door, _ = pointed_arch(-1.75, 1.75, 5.0, sharp=0.9, n=16)
        oc = [(1.9 * math.cos(a), 11.6 + 1.9 * math.sin(a))
              for a in [2 * math.pi * i / 32 for i in range(32)]]
        W = AISLE_X + WALL_T
        outer = [(-W, 0), (-1.75, 0)] + door + [(1.75, 0), (W, 0), (W, 24), (-W, 24)]
        slab("west_wall", self.col, self.m_stone, outer, [oc], frame_w, 1.4)
        outer = [(-W, 0), (W, 0), (W, 24), (-W, 24)]
        pts = [(u, Y_WEST - 0.02, v) for u, v in door]
        curve_obj("door_mould", self.col, self.m_stone, pts, 0.16)
        curve_obj("oculus_mould", self.col, self.m_stone,
                  [(x, Y_WEST - 0.02, z) for x, z in oc], 0.15, closed=True)
        # east wall with the rose window opening
        def frame_e(u, v, w):
            return Vector((u, Y_EAST + w, v))

        self.rose_c = Vector((0, Y_EAST, 13.8))
        self.rose_r = 4.3
        rose = [(self.rose_r * math.cos(a), 13.8 + self.rose_r * math.sin(a))
                for a in [2 * math.pi * i / 48 for i in range(48)]]
        slab("east_wall", self.col, self.m_stone, outer, [rose], frame_e, 1.4)

    def vault(self):
        """Pointed barrel vault with transverse ribs and a ragged collapse."""
        hole = self.info["hole"]
        rnd = random.Random(3)
        span_u0, span_u1 = -NAVE_X + WALL_T / 2, NAVE_X - WALL_T / 2
        arch, peak = pointed_arch(span_u0, span_u1, VAULT_SPRING, sharp=0.75, n=20)
        self.vault_peak = peak
        ny = int((Y_EAST - Y_WEST) / 0.5)
        bm = bmesh.new()
        grid = []
        for j in range(ny + 1):
            y = Y_WEST + (Y_EAST - Y_WEST) * j / ny
            grid.append([bm.verts.new((x, y, z)) for x, z in arch])
        # ragged outline: radius modulated by a few random harmonics
        harm = [(k, rnd.uniform(0.04, 0.13), rnd.uniform(0, 2 * math.pi)) for k in range(2, 8)]

        def in_hole(x, y):
            dx, dy = x - hole.x, (y - hole.y) * 0.8
            a = math.atan2(dy, dx)
            rr = 2.6 * (1 + sum(amp * math.sin(k * a + ph) for k, amp, ph in harm))
            return math.hypot(dx, dy) < rr

        for j in range(ny):
            for i in range(len(arch) - 1):
                vs = (grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i])
                c = sum((v.co for v in vs), Vector()) / 4
                if not in_hole(c.x, c.y):
                    bm.faces.new(vs)
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        o = mesh_obj("vault", bm, self.col, self.m_stone_rough, smooth=True)
        mod = o.modifiers.new("solid", "SOLIDIFY")
        mod.thickness = 0.45
        mod.offset = 1.0
        # transverse ribs, broken where the vault fell
        for y in PIER_YS:
            pts = [(x - 0.0, y, z - 0.05) for x, z in arch]
            seg, segs = [], []
            for p in pts:
                if in_hole(p[0], p[1]) and abs(y - hole.y) < 3.5:
                    if len(seg) > 1:
                        segs.append(seg)
                    seg = []
                else:
                    seg.append(p)
            if len(seg) > 1:
                segs.append(seg)
            for s in segs:
                curve_obj(f"rib_{y}", self.col, self.m_stone, s, 0.2, res=2)
        # ridge rib
        segs, seg = [], []
        for j in range(ny + 1):
            y = Y_WEST + (Y_EAST - Y_WEST) * j / ny
            if in_hole(0.0, y):
                if len(seg) > 1:
                    segs.append(seg)
                seg = []
            else:
                seg.append((0.0, y, peak - 0.1))
        if len(seg) > 1:
            segs.append(seg)
        for s in segs:
            curve_obj("ridge", self.col, self.m_stone, s, 0.14, res=2)
        self.in_hole = in_hole

    def sanctuary(self):
        w = 2 * NAVE_X - WALL_T
        box("step1", self.col, self.m_stone_rough, (w, Y_EAST - SANCTUARY_Y, 0.22),
            (0, (Y_EAST + SANCTUARY_Y) / 2, 0.11))
        box("step2", self.col, self.m_stone_rough, (w, Y_EAST - SANCTUARY_Y - 0.6, 0.44),
            (0, (Y_EAST + SANCTUARY_Y + 0.6) / 2, 0.22))
        box("altar", self.col, self.m_stone, (2.6, 1.1, 1.05), (0, 20.4, 0.44 + 0.52), bevel=0.03)
        box("altar_top", self.col, self.m_stone_rough, (2.9, 1.3, 0.12), (0, 20.4, 0.44 + 1.1), bevel=0.02)
        # altar cloth draped over the front
        bm = bmesh.new()
        bm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_grid(bm, x_segments=12, y_segments=8, size=0.5, calc_uvs=True)
        for v in bm.verts:
            v.co = Vector((v.co.x * 2.2, -0.59 - 0.015 * math.sin(v.co.x * 22),
                           0.16 + (v.co.y + 0.5) * 0.95))
        o = mesh_obj("altar_cloth", bm, self.col, self.m_banner, smooth=True)
        o.location = (0, 20.4, 0.44)

    def rose_window(self):
        c, r = self.rose_c, self.rose_r
        y = Y_EAST + 0.7
        mat = self.m_stone
        ring = lambda rad, n=64: [(c.x + rad * math.cos(a), y, c.z + rad * math.sin(a))
                                  for a in [2 * math.pi * i / n for i in range(n)]]
        curve_obj("rose_outer", self.col, mat, ring(r - 0.05), 0.22, closed=True)
        curve_obj("rose_inner", self.col, mat, ring(1.15), 0.14, closed=True)
        curve_obj("rose_hub", self.col, mat, ring(0.35, 24), 0.1, closed=True)
        for k in range(16):
            a = 2 * math.pi * k / 16
            curve_obj("rose_spoke", self.col, mat,
                      [(c.x + 1.15 * math.cos(a), y, c.z + 1.15 * math.sin(a)),
                       (c.x + (r - 0.1) * math.cos(a), y, c.z + (r - 0.1) * math.sin(a))], 0.07)
            a2 = a + math.pi / 16
            cc = (c.x + 2.95 * math.cos(a2), c.z + 2.95 * math.sin(a2))
            curve_obj("rose_foil", self.col, mat,
                      [(cc[0] + 0.55 * math.cos(b), y, cc[1] + 0.55 * math.sin(b))
                       for b in [2 * math.pi * i / 20 for i in range(20)]], 0.05, closed=True)
        # stained glass disc just behind the tracery
        bpy.ops.mesh.primitive_circle_add(vertices=64, radius=r, fill_type="NGON",
                                          location=(c.x, Y_EAST + 0.95, c.z), rotation=(math.pi / 2, 0, 0))
        g = bpy.context.active_object
        for cl in list(g.users_collection):
            cl.objects.unlink(g)
        self.col.objects.link(g)
        g.name = "rose_glass"
        g.data.materials.append(M.stained_glass())
        self.rose_glass = g

    def doors(self):
        # two heavy leaves swung inwards
        for side in (-1, 1):
            piv = link(bpy.data.objects.new(f"door_pivot_{side}", None), self.col)
            piv.location = (side * 1.75, Y_WEST - 0.1, 0)
            piv.rotation_euler = (0, 0, side * math.radians(-96))
            o = box(f"door_{side}", self.col, self.m_wood, (1.72, 0.14, 5.0), (-side * 0.86, 0.0, 2.5))
            o.parent = piv
            for zb in (0.8, 2.4, 4.0):
                b = box("door_band", self.col, self.m_iron, (1.74, 0.17, 0.09), (0, 0, zb - 2.5))
                b.parent = o

    def pews(self):
        rnd = random.Random(11)
        me = None
        bm = bmesh.new()
        L = 2.8
        for (sx, sy, sz, lx, ly, lz) in [
            (L, 0.42, 0.06, 0, 0, 0.45),            # seat
            (L, 0.06, 0.5, 0, -0.2, 0.78),          # back
            (0.07, 0.55, 1.02, -L / 2, 0, 0.51),    # end panels
            (0.07, 0.55, 1.02, L / 2, 0, 0.51),
            (L, 0.04, 0.2, 0, 0.18, 0.3),           # kneeler rail
        ]:
            res = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=res["verts"])
            bmesh.ops.translate(bm, vec=(lx, ly, lz), verts=res["verts"])
        me = bpy.data.meshes.new("pew")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(self.m_wood)
        stop_y = self.info["stop_y"]
        y = -14.6
        row = 0
        while y < 13.0:
            for side in (-1, 1):
                if self.in_hole(side * 2.8, y) or (abs(y - self.info["hole"].y) < 3.8 and rnd.random() < 0.8):
                    continue
                o = link(bpy.data.objects.new(f"pew_{row}_{side}", me), self.col)
                x = side * (1.4 + L / 2) + rnd.uniform(-0.06, 0.06)
                o.location = (x, y + rnd.uniform(-0.05, 0.05), 0)
                o.rotation_euler = (0, 0, math.radians(rnd.uniform(-2.5, 2.5)))
                r = rnd.random()
                if r < 0.08 and abs(y - stop_y) > 2.0:
                    o.rotation_euler = (math.radians(-82), 0, math.radians(rnd.uniform(-20, 20)))
                    o.location.z = 0.22
                    o.location.y -= 0.3
                elif r < 0.18:
                    o.rotation_euler = (0, 0, math.radians(rnd.uniform(-14, 14)))
            y += 1.18
            row += 1

    def rubble(self):
        hole = self.info["hole"]
        rnd = random.Random(5)
        bm = bmesh.new()
        # heap under the collapse (the hole projects down onto y ~ hole.y)
        for i in range(70):
            a = rnd.uniform(0, 2 * math.pi)
            d = abs(rnd.gauss(0, 1.7))
            cx = hole.x * 0.6 + d * math.cos(a)
            cy = hole.y + d * math.sin(a) * 1.3
            s = rnd.uniform(0.25, 1.0) * (1.4 - min(d, 3) / 3)
            rock(bm, (s * rnd.uniform(0.8, 1.6), s * rnd.uniform(0.8, 1.6), s * rnd.uniform(0.5, 0.9)),
                 i, (cx, cy, s * 0.25 + max(0, 0.6 - d * 0.25)),
                 (rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), rnd.uniform(0, 3.1)))
        # scattered debris along the nave, kept off her path
        for i in range(160):
            x = rnd.uniform(-8.8, 8.8)
            if abs(x) < 0.7:
                x = math.copysign(0.7 + rnd.random() * 0.6, x)
            yy = rnd.uniform(Y_WEST + 1, 15)
            s = rnd.uniform(0.04, 0.18)
            rock(bm, (s * 1.3, s, s * 0.7), 1000 + i, (x, yy, s * 0.3),
                 (0, 0, rnd.uniform(0, 3.1)))
        mesh_obj("rubble", bm, self.col, self.m_rubble)
        # a fallen rib segment leaning on the heap
        pts = [(hole.x * 0.5 - 1.8 + 3.6 * t, hole.y - 0.6 + 1.2 * t, 0.3 + 1.6 * math.sin(math.pi * t) * 0.6)
               for t in [i / 8 for i in range(9)]]
        curve_obj("fallen_rib", self.col, self.m_stone, pts, 0.22, res=2)

    def banners(self):
        hang = [(-1, -15.0), (1, -11.0), (-1, -7.0), (1, -3.0), (-1, 1.0), (1, 9.0)]
        rnd = random.Random(2)
        for i, (side, y) in enumerate(hang):
            bm = bmesh.new()
            bm.loops.layers.uv.new("UVMap")
            bmesh.ops.create_grid(bm, x_segments=10, y_segments=36, size=0.5, calc_uvs=True)
            for v in bm.verts:
                u, t = v.co.x + 0.5, v.co.y + 0.5  # t: 0 bottom .. 1 top
                fold = 0.05 * math.sin(u * 14 + i) * (1.2 - t) + 0.03 * math.sin(t * 9 + i * 2)
                v.co = Vector((side * fold, (u - 0.5) * 1.0, 10.1 - (1 - t) * 3.6 - 0.15 * (1 - t) ** 2))
            o = mesh_obj(f"banner_{i}", bm, self.col, self.m_banner, smooth=True)
            o.location = (side * (NAVE_X - WALL_T / 2 - 0.12), y, 0)
            o.rotation_euler = (0, math.radians(side * rnd.uniform(1, 4)), 0)
            box("banner_rod", self.col, self.m_iron, (0.06, 1.25, 0.06),
                (side * (NAVE_X - WALL_T / 2 - 0.14), y, 10.12))

    def _candle_cluster(self, name, loc, n, seed, radius=0.25, light_w=18.0, h_scale=1.0):
        rnd = random.Random(seed)
        bm = bmesh.new()
        flames = bmesh.new()
        lx, ly, lz = loc
        top = 0.0
        for i in range(n):
            a = rnd.uniform(0, 2 * math.pi)
            d = radius * math.sqrt(rnd.random())
            x, y = lx + d * math.cos(a), ly + d * math.sin(a)
            r = rnd.uniform(0.018, 0.035)
            h = rnd.uniform(0.06, 0.32) * h_scale
            cylinder(bm, r, h, lz, segs=10, x=x, y=y)
            # melted lip
            cylinder(bm, r * 1.12, 0.012, lz + h - 0.012, segs=10, x=x, y=y)
            res = bmesh.ops.create_uvsphere(flames, u_segments=8, v_segments=6, radius=1.0)
            bmesh.ops.scale(flames, vec=(0.007, 0.007, 0.02), verts=res["verts"])
            bmesh.ops.translate(flames, vec=(x, y, lz + h + 0.024), verts=res["verts"])
            top = max(top, lz + h)
        mesh_obj(name + "_wax", bm, self.col, self.m_wax, smooth=True)
        fl = mesh_obj(name + "_flame", flames, self.col, self.m_flame, smooth=True)
        fl.visible_shadow = False
        L = bpy.data.lights.new(name + "_light", "POINT")
        L.energy = light_w
        L.color = (1.0, 0.52, 0.2)
        L.shadow_soft_size = 0.05
        lo = link(bpy.data.objects.new(name + "_light", L), self.col)
        lo.location = (lx, ly, top + 0.06)
        # flicker
        for f in range(1, 900, 3):
            fr = random.Random(seed * 1000 + f)
            L.energy = light_w * (0.82 + 0.3 * fr.random())
            L.keyframe_insert("energy", frame=f)
        return lo

    def candles(self):
        self.candle_lights = []
        spots = [
            ("c_door_l", (-2.6, -18.6, 0), 9, 0.3, 14), ("c_door_r", (2.9, -19.4, 0), 7, 0.25, 12),
            ("c_pier_a", (-4.3, -13.0, 0.35), 8, 0.22, 14), ("c_pier_b", (4.3, -9.0, 0.35), 6, 0.2, 12),
            ("c_aisle_l", (-1.25, -7.3, 0), 10, 0.3, 16), ("c_aisle_r", (1.3, -4.4, 0), 8, 0.25, 14),
            ("c_pier_c", (-4.3, -1.0, 0.35), 7, 0.2, 12), ("c_pier_d", (4.3, 7.0, 0.35), 7, 0.2, 12),
            ("c_altar_l", (-1.0, 20.25, 1.6), 9, 0.2, 18), ("c_altar_r", (1.0, 20.35, 1.6), 9, 0.2, 18),
            ("c_steps_l", (-3.0, 17.0, 0.44), 14, 0.45, 22), ("c_steps_r", (3.2, 16.9, 0.44), 12, 0.4, 20),
        ]
        spots += self.info.get("candle_spots", [])
        for i, (name, loc, n, rad, w) in enumerate(spots):
            self.candle_lights.append(self._candle_cluster(name, loc, n, 100 + i, rad, w))

    def fog(self):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(2 * AISLE_X + 1.6, Y_EAST - Y_WEST + 1.2, 25.0), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, (Y_EAST + Y_WEST) / 2, 12.5), verts=bm.verts)
        self.fog_obj = mesh_obj("fog_interior", bm, self.col, M.fog(density=0.014, anisotropy=0.4))
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(60, 40, 30), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, Y_WEST - 1.45 - 20.1, 15), verts=bm.verts)
        mesh_obj("fog_exterior", bm, self.col,
                 M.fog("M_fog_out", density=0.03, anisotropy=0.3, color=(0.8, 0.86, 1.0),
                       emission=0.005, emission_color=(0.35, 0.45, 0.7)))

    def motes(self):
        """Dust drifting in the moonbeam: instanced specks animated in Geometry Nodes."""
        rnd = random.Random(9)
        stop_y = self.info["stop_y"]
        beam = self.info["beam_dir"]
        pts = []
        for i in range(1400):
            t = rnd.uniform(0.0, 6.0)
            rr = 1.4 * math.sqrt(rnd.random())
            a = rnd.uniform(0, 2 * math.pi)
            p = Vector((rr * math.cos(a), stop_y + rr * math.sin(a), 0)) + beam * t
            pts.append(p)
        for i in range(600):
            pts.append(Vector((rnd.uniform(-4, 4), rnd.uniform(stop_y - 14, stop_y + 6), rnd.uniform(0.2, 5))))
        me = bpy.data.meshes.new("motes")
        me.from_pydata([tuple(p) for p in pts], [], [])
        o = link(bpy.data.objects.new("motes", me), self.col)
        ng = bpy.data.node_groups.new("MoteDrift", "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        N = ng.nodes
        gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
        pos = N.new("GeometryNodeInputPosition")
        tm = N.new("GeometryNodeInputSceneTime")
        noise = N.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "4D"
        noise.inputs["Scale"].default_value = 0.35
        noise.inputs["Detail"].default_value = 1.0
        wmul = N.new("ShaderNodeMath")
        wmul.operation = "MULTIPLY"
        wmul.inputs[1].default_value = 0.03
        ng.links.new(tm.outputs["Seconds"], wmul.inputs[0])
        ng.links.new(pos.outputs["Position"], noise.inputs["Vector"])
        ng.links.new(wmul.outputs[0], noise.inputs["W"])
        sub = N.new("ShaderNodeVectorMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = (0.5, 0.5, 0.5)
        ng.links.new(noise.outputs["Color"], sub.inputs[0])
        amp = N.new("ShaderNodeVectorMath")
        amp.operation = "SCALE"
        amp.name = "mote_amp"
        amp.inputs["Scale"].default_value = 1.6
        ng.links.new(sub.outputs[0], amp.inputs[0])
        # slow upward drift
        drift = N.new("ShaderNodeVectorMath")
        drift.operation = "SCALE"
        drift.inputs[0].default_value = (0.0, 0.0, 0.035)
        ng.links.new(tm.outputs["Seconds"], drift.inputs["Scale"])
        add = N.new("ShaderNodeVectorMath")
        add.operation = "ADD"
        ng.links.new(amp.outputs[0], add.inputs[0])
        ng.links.new(drift.outputs[0], add.inputs[1])
        setp = N.new("GeometryNodeSetPosition")
        ng.links.new(gi.outputs[0], setp.inputs["Geometry"])
        ng.links.new(add.outputs[0], setp.inputs["Offset"])
        ico = N.new("GeometryNodeMeshIcoSphere")
        ico.inputs["Radius"].default_value = 1.0
        ico.inputs["Subdivisions"].default_value = 1
        rv = N.new("FunctionNodeRandomValue")
        rv.data_type = "FLOAT"
        fin = lambda socks, nm: next(s for s in socks if s.name == nm and s.type == "VALUE" and s.enabled)
        fin(rv.inputs, "Min").default_value = 0.0018
        fin(rv.inputs, "Max").default_value = 0.0045
        inst = N.new("GeometryNodeInstanceOnPoints")
        ng.links.new(setp.outputs["Geometry"], inst.inputs["Points"])
        ng.links.new(ico.outputs["Mesh"], inst.inputs["Instance"])
        ng.links.new(fin(rv.outputs, "Value"), inst.inputs["Scale"])
        smat = N.new("GeometryNodeSetMaterial")
        smat.inputs["Material"].default_value = M.mote()
        ng.links.new(inst.outputs["Instances"], smat.inputs["Geometry"])
        ng.links.new(smat.outputs["Geometry"], go.inputs[0])
        mod = o.modifiers.new("drift", "NODES")
        mod.node_group = ng
        self.motes_obj = o
