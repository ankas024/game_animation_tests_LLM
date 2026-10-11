"""Scene setup: ch_02 + uploaded textures + spear prop (bones, mesh, texture)."""
import math
import os

import bpy  # noqa: I001  (bpy must be imported before bmesh)
import bmesh
from mathutils import Matrix, Vector

import rig as R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHAR_FBX = os.path.join(ROOT, "assets/skeletal_meshes/characters/ch_02.fbx")
TEX = {
    "M_c002_body": os.path.join(ROOT, "assets/textures/SK_c002_tripo_rgb_69d181a3-f4af-4255-8e04-1ec596474e7e.jpg"),
    "M_c002_head": os.path.join(ROOT, "assets/textures/SK_c002_face_text_fix.png"),
}
SPEAR_TEX = os.path.join(ROOT, "assets/textures/T_Spear.png")
SPEAR_REST_CENTRE = Vector((-0.6, 0.0, R.SPEAR_LEN / 2))

# texture atlas columns (u ranges) for the spear parts
SILVER, BLUE, DARK = 0.125, 0.375, 0.625


def load_character():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=CHAR_FBX)
    for o in list(bpy.data.objects):
        if o.name == "Icosphere":
            bpy.data.objects.remove(o)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    for mn, path in TEX.items():
        m = bpy.data.materials.get(mn)
        if m is None:
            continue
        img = bpy.data.images.load(path, check_existing=True)
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE":
                n.image = img
    # drop the dangling original image reference
    for im in list(bpy.data.images):
        if im.users == 0:
            bpy.data.images.remove(im)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    return arm


def add_spear_bones(arm):
    if R.SPEAR in arm.data.bones:
        return
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    inv = arm.matrix_world.inverted()
    inv3 = inv.to_3x3()
    up = Vector((0, 0, 1))
    prev = eb[R.P + "Hips"]
    for i, n in enumerate(R.SPEAR_FWD):
        b = eb.new(n)
        b.head = inv @ (SPEAR_REST_CENTRE + up * (R.SEG * i))
        b.tail = inv @ (SPEAR_REST_CENTRE + up * (R.SEG * (i + 1)))
        b.align_roll(inv3 @ Vector((0, -1, 0)))
        b.parent = prev
        prev = b
    prev = eb[R.SPEAR]
    for i, n in enumerate(R.SPEAR_BACK):
        b = eb.new(n)
        b.head = inv @ (SPEAR_REST_CENTRE - up * (R.SEG * i))
        b.tail = inv @ (SPEAR_REST_CENTRE - up * (R.SEG * (i + 1)))
        b.align_roll(inv3 @ Vector((0, 1, 0)))
        b.parent = prev
        prev = b
    bpy.ops.object.mode_set(mode="OBJECT")


def _spear_texture():
    if os.path.exists(SPEAR_TEX):
        return bpy.data.images.load(SPEAR_TEX, check_existing=True)
    w, h = 64, 8
    img = bpy.data.images.new("T_Spear", w, h)
    cols = [(0.80, 0.82, 0.86), (0.10, 0.38, 0.95), (0.16, 0.18, 0.24), (0.55, 0.75, 1.0)]
    px = []
    for y in range(h):
        for x in range(w):
            r, g, b = cols[x * 4 // w]
            px += [r, g, b, 1.0]
    img.pixels = px
    img.filepath_raw = SPEAR_TEX
    img.file_format = "PNG"
    img.save()
    return img


def _part(bm, verts_faces, u):
    """Add a list of (verts, faces) to bm with a flat UV column u."""
    uv = bm.loops.layers.uv.verify()
    for vs, fs in verts_faces:
        bv = [bm.verts.new(v) for v in vs]
        for f in fs:
            try:
                face = bm.faces.new([bv[i] for i in f])
            except ValueError:
                continue
            for lp in face.loops:
                lp[uv].uv = (u, 0.5)


def _tube(z0, z1, r0, r1, n=12, segs=1):
    vs, fs = [], []
    for k in range(segs + 1):
        u = k / segs
        z, r = z0 + (z1 - z0) * u, r0 + (r1 - r0) * u
        for i in range(n):
            a = 2 * math.pi * i / n
            vs.append((r * math.cos(a), r * math.sin(a), z))
    for k in range(segs):
        for i in range(n):
            j = (i + 1) % n
            fs.append((k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i))
    c0, c1 = len(vs), len(vs) + 1
    vs += [(0, 0, z0), (0, 0, z1)]
    top = segs * n
    for i in range(n):
        j = (i + 1) % n
        fs.append((c0, j, i))
        fs.append((c1, top + i, top + j))
    return vs, fs


def _slab(outline, th):
    """Extrude a 2D outline (in the x/z plane of the spear) by thickness th along y."""
    n = len(outline)
    vs = [(x, -th / 2, z) for x, z in outline] + [(x, th / 2, z) for x, z in outline]
    fs = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        fs.append((i, n + i, n + j, j))
    return vs, fs


def build_spear_mesh(arm):
    """Spear along local +Z (blade up), centre at the origin. Blade flat in x/z."""
    L = R.SPEAR_LEN
    half = L / 2
    bm = bmesh.new()
    # shaft and fittings
    _part(bm, [_tube(-half + 0.10, half - 0.30, 0.012, 0.012, 14, 36)], SILVER)
    for z, ln, r in ((half - 0.32, 0.06, 0.019), (-half + 0.08, 0.05, 0.018), (0.25, 0.03, 0.016),
                     (-0.25, 0.03, 0.016)):
        _part(bm, [_tube(z, z + ln, r, r, 14)], BLUE)
    _part(bm, [_tube(half - 0.26, half - 0.24, 0.02, 0.014, 14)], DARK)
    # blade: central leaf + two side wings (trident-like head), blue
    leaf = [(0.0, half - 0.26), (0.032, half - 0.20), (0.026, half - 0.10), (0.0, half),
            (-0.026, half - 0.10), (-0.032, half - 0.20)]
    _part(bm, [_slab(leaf, 0.010)], BLUE)
    for sx in (1, -1):
        wing = [(sx * 0.015, half - 0.27), (sx * 0.075, half - 0.24), (sx * 0.085, half - 0.15),
                (sx * 0.060, half - 0.20), (sx * 0.018, half - 0.22)]
        if sx < 0:
            wing = wing[::-1]
        _part(bm, [_slab(wing, 0.008)], BLUE)
    # butt: crescent fork, horns pointing away from the shaft
    zc, ro = -half + 0.058, 0.052
    outer, inner = [], []
    for i in range(13):
        a = -40.0 + 260.0 * i / 12
        t = 0.004 + 0.018 * max(0.0, 1.0 - abs(a - 90.0) / 130.0)
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        outer.append((ro * ca, zc + ro * sa))
        inner.append(((ro - t) * ca, zc + (ro - t) * sa))
    _part(bm, [_slab(outer + inner[::-1], 0.012)], BLUE)
    _part(bm, [_tube(-half + 0.04, -half + 0.11, 0.008, 0.016, 12)], SILVER)
    me = bpy.data.meshes.new("SM_Spear")
    bm.to_mesh(me)
    bm.free()
    mat = bpy.data.materials.new("M_Spear")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = _spear_texture()
    tex.interpolation = "Closest"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.6
    bsdf.inputs["Roughness"].default_value = 0.35
    me.materials.append(mat)
    ob = bpy.data.objects.new("SM_Spear", me)
    bpy.context.scene.collection.objects.link(ob)
    # rest placement: vertical at SPEAR_REST_CENTRE (matches the spear bones' rest pose)
    ob.matrix_world = Matrix.Translation(SPEAR_REST_CENTRE)
    # skin: tent weights over the bone chain by arclength
    chain = [(n, -R.SEG * (i + 0.5)) for i, n in enumerate(R.SPEAR_BACK)] + \
            [(n, R.SEG * (i + 0.5)) for i, n in enumerate(R.SPEAR_FWD)]
    groups = {n: ob.vertex_groups.new(name=n) for n, _ in chain}
    for v in me.vertices:
        s = v.co.z
        ws = [(n, max(0.0, 1.0 - abs(s - m) / R.SEG)) for n, m in chain]
        tot = sum(w for _, w in ws)
        if tot < 1e-6:  # beyond the outer bone midpoints
            n = chain[0][0] if s < 0 else chain[-1][0]
            groups[n].add([v.index], 1.0, "REPLACE")
            continue
        for n, w in ws:
            if w > 0:
                groups[n].add([v.index], w / tot, "REPLACE")
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.matrix_world = mw
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return ob


def setup(with_spear=True):
    arm = load_character()
    if with_spear:
        add_spear_bones(arm)
        build_spear_mesh(arm)
    for p in arm.pose.bones:
        p.rotation_mode = "QUATERNION"
    return arm


def _srgb_to_lin(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def _flat_image(name, rgb):
    img = bpy.data.images.new(name, 4, 4)
    img.pixels = list(rgb) * 0 + [v for _ in range(16) for v in (*rgb, 1.0)]
    return img


def setup_workbench(res=(640, 360), bg=(0.643, 0.686, 0.714), floor=(1.0, 1.0, 1.0),
                    light="outdoor.sl"):
    """Solid-view textured shading (Workbench): what the viewport shows in
    Solid mode with Color = Texture. bg / floor are display (sRGB) colours."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.studio_light = light
    sh.color_type = "TEXTURE"
    sh.show_shadows = True
    sh.shadow_intensity = 0.3
    sh.show_cavity = False
    sh.show_specular_highlight = True
    sc.display.light_direction = (0.45, -0.35, 0.82)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("bg")
    w.color = _srgb_to_lin(bg)
    sc.world = w
    sh.background_type = "WORLD"
    if "Floor" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
        fl = bpy.context.active_object
        fl.name = "Floor"
        m = bpy.data.materials.new("M_Floor")
        m.use_nodes = True
        nt = m.node_tree
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = _flat_image("T_Floor", floor)
        nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        fl.data.materials.append(m)
    return sc
