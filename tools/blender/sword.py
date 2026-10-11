"""Procedural placeholder sword (NieR-ish straight single-edged blade).

Local frame (also the weapon_r bone frame):
    origin = centre of the fist on the grip
    +Y     = towards the tip
    +X     = cutting edge side
    +Z     = flat of the blade
"""
import math
import bmesh
import bpy
from mathutils import Vector, Matrix

BLADE_START = 0.062
BLADE_END = 0.765
TIP_START = 0.655
SPINE_X = -0.014
GUARD_Y0, GUARD_Y1 = 0.042, 0.062
GRIP_Y0 = -0.105
POMMEL_Y0 = -0.135


def _ring(bm, pts, y):
    return [bm.verts.new((x, y, z)) for (x, z) in pts]


def _bridge(bm, a, b, mat=0):
    n = len(a)
    for i in range(n):
        f = bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        f.material_index = mat
        f.smooth = False


def _cap(bm, ring, mat=0, flip=False):
    f = bm.faces.new(list(reversed(ring)) if flip else ring)
    f.material_index = mat
    return f


def blade_section(width, thick, edge_thick=0.0006):
    """single-edged blade: thick spine at -x, ridge line, sharp edge at +x."""
    x0 = SPINE_X
    x1 = x0 + width * 0.42      # shinogi (ridge) line
    x2 = x0 + width
    return [
        (x0, -thick * 0.42), (x1, -thick * 0.5), (x2, -edge_thick),
        (x2, edge_thick), (x1, thick * 0.5), (x0, thick * 0.42),
    ]


def build_mesh(name="SM_Sword_Placeholder"):
    bm = bmesh.new()
    # --- blade --------------------------------------------------------
    rings = []
    ys = [BLADE_START + (TIP_START - BLADE_START) * i / 6 for i in range(7)]
    for y in ys:
        u = (y - BLADE_START) / (TIP_START - BLADE_START)
        w = 0.035 - 0.006 * u
        t = 0.0075 - 0.0015 * u
        rings.append(_ring(bm, blade_section(w, t), y))
    # tip: the edge sweeps up to meet the straight spine (kissaki-like)
    w_tip0 = 0.029
    t_tip0 = 0.006
    for i in range(1, 7):
        u = i / 7
        y = TIP_START + (BLADE_END - TIP_START) * u
        w = w_tip0 * math.cos(u * math.pi / 2) ** 0.8 + 0.0015
        t = t_tip0 * (1 - u) + 0.0012
        rings.append(_ring(bm, blade_section(w, t), y))
    for a, b in zip(rings, rings[1:]):
        _bridge(bm, a, b, mat=0)
    tip = bm.verts.new((SPINE_X + 0.0005, BLADE_END + 0.012, 0.0))
    last = rings[-1]
    for i in range(len(last)):
        f = bm.faces.new((last[i], last[(i + 1) % len(last)], tip))
        f.material_index = 0
    _cap(bm, rings[0], mat=0, flip=True)

    # glowing core line (a thin inset strip on both flats; separate material)
    for zs in (1, -1):
        strip = []
        for y in (BLADE_START + 0.03, TIP_START - 0.01):
            u = (y - BLADE_START) / (TIP_START - BLADE_START)
            t = (0.0075 - 0.0015 * u) * 0.5 + 0.0004
            x0 = SPINE_X + 0.006
            strip.append((bm.verts.new((x0, y, zs * t)), bm.verts.new((x0 + 0.0035, y, zs * t))))
        f = bm.faces.new((strip[0][0], strip[0][1], strip[1][1], strip[1][0]) if zs > 0 else
                         (strip[0][1], strip[0][0], strip[1][0], strip[1][1]))
        f.material_index = 2

    # --- guard: squared, slightly asymmetric -------------------------------
    def box(x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
        vs = [bm.verts.new(v) for v in (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
        for idx in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            f = bm.faces.new([vs[i] for i in idx])
            f.material_index = mat
        return vs

    box(-0.040, 0.050, GUARD_Y0, GUARD_Y1, -0.016, 0.016, 1)
    box(-0.022, 0.032, GUARD_Y1, GUARD_Y1 + 0.006, -0.011, 0.011, 1)

    # --- grip: octagonal, slightly waisted -------------------------------
    grip_rings = []
    n = 8
    for i, y in enumerate([GRIP_Y0, -0.06, -0.01, GUARD_Y0]):
        r = (0.0135, 0.0125, 0.0128, 0.0135)[i]
        pts = [(r * 1.05 * math.cos(2 * math.pi * k / n + math.pi / 8) + 0.001,
                r * 0.85 * math.sin(2 * math.pi * k / n + math.pi / 8)) for k in range(n)]
        grip_rings.append(_ring(bm, pts, y))
    for a, b in zip(grip_rings, grip_rings[1:]):
        _bridge(bm, a, b, mat=3)
    _cap(bm, grip_rings[-1], mat=3)

    # --- pommel: faceted diamond ---------------------------------------------
    pr = []
    for y, r in ((GRIP_Y0, 0.0155), (GRIP_Y0 - 0.012, 0.019), (POMMEL_Y0, 0.009)):
        pts = [(r * math.cos(2 * math.pi * k / 6) + 0.001, r * 0.8 * math.sin(2 * math.pi * k / 6))
               for k in range(6)]
        pr.append(_ring(bm, pts, y))
    for a, b in zip(pr, pr[1:]):
        _bridge(bm, a, b, mat=1)
    _cap(bm, pr[0], mat=1, flip=True)
    _cap(bm, pr[-1], mat=1)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    # 0 at the pommel -> 1 at the tip; drives the materialise / dissolve shader
    attr = me.attributes.new("blade_t", 'FLOAT', 'POINT')
    y0, y1 = POMMEL_Y0, BLADE_END + 0.012
    attr.data.foreach_set("value", [(v.co.y - y0) / (y1 - y0) for v in me.vertices])
    return me


def make_materials():
    """Simple PBR placeholder materials (preview render swaps blade shader)."""
    mats = []
    spec = [("M_Sword_Blade", (0.86, 0.86, 0.84, 1), 0.9, 0.18),
            ("M_Sword_Guard", (0.05, 0.05, 0.055, 1), 0.8, 0.35),
            ("M_Sword_Core", (0.6, 0.95, 1.0, 1), 0.0, 0.3),
            ("M_Sword_Grip", (0.02, 0.02, 0.022, 1), 0.0, 0.7)]
    for name, col, metal, rough in spec:
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Metallic"].default_value = metal
        bsdf.inputs["Roughness"].default_value = rough
        m.diffuse_color = col
        mats.append(m)
    return mats


def build_skinned(arm, rig, weapon_bone="weapon_r"):
    """Sword mesh placed at the rest grip and skinned 100% to weapon_r."""
    from rigkit import K
    me = build_mesh()
    for m in make_materials():
        me.materials.append(m)
    obj = bpy.data.objects.new("SK_Sword_Placeholder", me)
    bpy.context.scene.collection.objects.link(obj)
    # local -> world at rest
    S = rig.sword_rest
    M = (K @ S).to_4x4()
    M.translation = K @ rig.grip_rest
    me.transform(M)
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()
    vg = obj.vertex_groups.new(name=weapon_bone)
    vg.add(list(range(len(me.vertices))), 1.0, 'REPLACE')
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    obj.color = (0.9, 0.9, 0.95, 1)
    return obj
