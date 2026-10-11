"""
Stylised preview render of the sword combo.

usage:
  python -I render_preview.py --out DIR [--engine EEVEE|CYCLES] [--frames a-b[:step]]
                              [--res 1280x720] [--samples N]
"""
import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402

import scene_util as su  # noqa: E402
import rigkit  # noqa: E402
import sword  # noqa: E402
import combo  # noqa: E402
import bake  # noqa: E402
import fx  # noqa: E402

BG = (0.010, 0.011, 0.014)


# ---------------------------------------------------------------------------
# node helpers
# ---------------------------------------------------------------------------
def new_mat(name):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k.startswith("_"):
            setattr(n, k[1:], v)
        else:
            n.inputs[k].default_value = v
    return n


def link(nt, a, b):
    nt.links.new(a, b)


def math_node(nt, op, a=None, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            link(nt, v, n.inputs[i])
    return n.outputs[0]


# ---------------------------------------------------------------------------
def character_material():
    m, nt, out = new_mat("M_Preview_Character")
    bsdf = node(nt, "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.20, 0.19, 0.185, 1)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Specular IOR Level"].default_value = 0.45
    bsdf.inputs["Sheen Weight"].default_value = 0.35
    bsdf.inputs["Sheen Tint"].default_value = (0.7, 0.8, 1.0, 1)
    # cavity-ish darkening from ambient occlusion
    ao = node(nt, "ShaderNodeAmbientOcclusion", Distance=0.04)
    mix = node(nt, "ShaderNodeMix", _data_type='RGBA', _blend_type='MULTIPLY', Factor=0.65)
    mix.inputs[6].default_value = (0.20, 0.19, 0.185, 1)
    link(nt, ao.outputs["Color"], mix.inputs[7])
    link(nt, mix.outputs[2], bsdf.inputs["Base Color"])
    link(nt, bsdf.outputs[0], out.inputs[0])
    return m


def sword_materials():
    """Shared dissolve mask for every sword material.
    reveal: -0.2..1.2 sweep, direction 0 = hilt->tip, 1 = tip->hilt."""
    grp = bpy.data.node_groups.new("SwordDissolve", "ShaderNodeTree")
    grp.interface.new_socket("Alpha", in_out='OUTPUT', socket_type='NodeSocketFloat')
    grp.interface.new_socket("Edge", in_out='OUTPUT', socket_type='NodeSocketFloat')
    gt = grp.nodes
    go = gt.new("NodeGroupOutput")
    attr = gt.new("ShaderNodeAttribute")
    attr.attribute_name = "blade_t"
    tc = gt.new("ShaderNodeTexCoord")
    noise = gt.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 55.0
    noise.inputs["Detail"].default_value = 3.0
    grp.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
    reveal = gt.new("ShaderNodeValue")
    reveal.name = "reveal"
    reveal.outputs[0].default_value = 1.3
    direction = gt.new("ShaderNodeValue")
    direction.name = "direction"
    direction.outputs[0].default_value = 0.0
    nt = grp
    inv = math_node(nt, 'SUBTRACT', 1.0, attr.outputs["Fac"])
    tmix = gt.new("ShaderNodeMix")
    tmix.data_type = 'FLOAT'
    grp.links.new(direction.outputs[0], tmix.inputs[0])
    grp.links.new(attr.outputs["Fac"], tmix.inputs[2])
    grp.links.new(inv, tmix.inputs[3])
    n_c = math_node(nt, 'SUBTRACT', noise.outputs["Fac"], 0.5)
    n_s = math_node(nt, 'MULTIPLY', n_c, 0.32)
    v = math_node(nt, 'ADD', tmix.outputs[0], n_s)
    # alpha = v < reveal
    alpha = math_node(nt, 'LESS_THAN', v, reveal.outputs[0])
    # edge band just behind the front
    dist = math_node(nt, 'SUBTRACT', reveal.outputs[0], v)
    e1 = math_node(nt, 'DIVIDE', dist, 0.09)
    e2 = math_node(nt, 'SUBTRACT', 1.0, e1, clamp=True)
    edge = math_node(nt, 'MULTIPLY', e2, alpha)
    grp.links.new(alpha, go.inputs["Alpha"])
    grp.links.new(edge, go.inputs["Edge"])

    spec = {
        "M_Sword_Blade": dict(col=(0.92, 0.93, 0.95), metal=0.6, rough=0.16, emit=0.06),
        "M_Sword_Guard": dict(col=(0.04, 0.04, 0.045), metal=0.7, rough=0.3, emit=0.0),
        "M_Sword_Core": dict(col=(0.6, 0.95, 1.0), metal=0.0, rough=0.3, emit=6.0),
        "M_Sword_Grip": dict(col=(0.02, 0.02, 0.022), metal=0.0, rough=0.6, emit=0.0),
    }
    mats = {}
    for name, p in spec.items():
        m, nt, out = new_mat("Preview_" + name)
        m.surface_render_method = 'DITHERED'
        g = nt.nodes.new("ShaderNodeGroup")
        g.node_tree = grp
        bsdf = node(nt, "ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = p["col"] + (1,)
        bsdf.inputs["Metallic"].default_value = p["metal"]
        bsdf.inputs["Roughness"].default_value = p["rough"]
        bsdf.inputs["Emission Color"].default_value = (0.75, 0.95, 1.0, 1)
        bsdf.inputs["Emission Strength"].default_value = p["emit"]
        glow = node(nt, "ShaderNodeEmission", Color=(0.55, 0.9, 1.0, 1), Strength=30.0)
        mix_e = node(nt, "ShaderNodeMixShader")
        link(nt, g.outputs["Edge"], mix_e.inputs[0])
        link(nt, bsdf.outputs[0], mix_e.inputs[1])
        link(nt, glow.outputs[0], mix_e.inputs[2])
        tr = node(nt, "ShaderNodeBsdfTransparent")
        mix_a = node(nt, "ShaderNodeMixShader")
        link(nt, g.outputs["Alpha"], mix_a.inputs[0])
        link(nt, tr.outputs[0], mix_a.inputs[1])
        link(nt, mix_e.outputs[0], mix_a.inputs[2])
        link(nt, mix_a.outputs[0], out.inputs[0])
        mats[name] = m
    return grp, mats


def fx_material(name, color, strength, kind):
    """Additive-looking emissive FX driven by the 'fx' colour attribute.
    trail:  R=age G=across B=speed weight ; shards: R=glow G=tint"""
    m, nt, out = new_mat(name)
    m.surface_render_method = 'BLENDED'
    m.use_backface_culling = False
    ca = node(nt, "ShaderNodeVertexColor", _layer_name="fx")
    sep = node(nt, "ShaderNodeSeparateColor")
    link(nt, ca.outputs["Color"], sep.inputs[0])
    R, G, B = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    if kind == "trail":
        fade = math_node(nt, 'POWER', math_node(nt, 'SUBTRACT', 1.0, R), 2.6)
        acr = math_node(nt, 'MULTIPLY', math_node(nt, 'POWER', G, 2.5), 0.55)
        a = math_node(nt, 'MULTIPLY', math_node(nt, 'MULTIPLY', fade, acr), B)
        hot = math_node(nt, 'POWER', G, 30.0)
        colmix = node(nt, "ShaderNodeMix", _data_type='RGBA')
        link(nt, hot, colmix.inputs[0])
        colmix.inputs[6].default_value = color + (1,)
        colmix.inputs[7].default_value = (1, 1, 1, 1)
        em = node(nt, "ShaderNodeEmission", Strength=strength)
        link(nt, colmix.outputs[2], em.inputs["Color"])
    elif kind == "ring":
        a1 = math_node(nt, 'POWER', G, 3.0)
        fade = node(nt, "ShaderNodeAttribute", _attribute_type='OBJECT', _attribute_name="fade")
        a = math_node(nt, 'MULTIPLY', a1, fade.outputs["Fac"])
        em = node(nt, "ShaderNodeEmission", Color=color + (1,), Strength=strength)
    else:
        a = R
        colmix = node(nt, "ShaderNodeMix", _data_type='RGBA')
        link(nt, G, colmix.inputs[0])
        colmix.inputs[6].default_value = color + (1,)
        colmix.inputs[7].default_value = (1.0, 0.85, 0.65, 1)
        em = node(nt, "ShaderNodeEmission", Strength=strength)
        link(nt, colmix.outputs[2], em.inputs["Color"])
    tr = node(nt, "ShaderNodeBsdfTransparent")
    add = node(nt, "ShaderNodeMixShader")
    link(nt, a, add.inputs[0])
    link(nt, tr.outputs[0], add.inputs[1])
    link(nt, em.outputs[0], add.inputs[2])
    link(nt, add.outputs[0], out.inputs[0])
    return m


def floor_material():
    m, nt, out = new_mat("M_Preview_Floor")
    bsdf = node(nt, "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.018, 0.019, 0.022, 1)
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    tc = node(nt, "ShaderNodeTexCoord")
    sep = node(nt, "ShaderNodeSeparateXYZ")
    link(nt, tc.outputs["Object"], sep.inputs[0])

    def line(c, scale, width):
        f = math_node(nt, 'FRACT', math_node(nt, 'MULTIPLY', c, scale))
        d = math_node(nt, 'MINIMUM', f, math_node(nt, 'SUBTRACT', 1.0, f))
        return math_node(nt, 'LESS_THAN', d, width)
    gx = line(sep.outputs[0], 2.0, 0.012)
    gy = line(sep.outputs[1], 2.0, 0.012)
    grid = math_node(nt, 'MAXIMUM', gx, gy)
    # radial fade around the action
    vlen = node(nt, "ShaderNodeVectorMath", _operation='LENGTH')
    sub = node(nt, "ShaderNodeVectorMath", _operation='SUBTRACT')
    link(nt, tc.outputs["Object"], sub.inputs[0])
    sub.inputs[1].default_value = (0.0, -0.3, 0.0)
    link(nt, sub.outputs[0], vlen.inputs[0])
    fade = math_node(nt, 'SUBTRACT', 1.0, math_node(nt, 'DIVIDE', vlen.outputs["Value"], 4.5), clamp=True)
    fade2 = math_node(nt, 'POWER', fade, 2.0)
    g = math_node(nt, 'MULTIPLY', grid, fade2)
    bsdf.inputs["Emission Color"].default_value = (0.35, 0.6, 0.75, 1)
    link(nt, math_node(nt, 'MULTIPLY', g, 0.10), bsdf.inputs["Emission Strength"])
    link(nt, bsdf.outputs[0], out.inputs[0])
    return m


def world_setup():
    w = bpy.data.worlds.new("W_Preview")
    bpy.context.scene.world = w
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = node(nt, "ShaderNodeTexCoord")
    sep = node(nt, "ShaderNodeSeparateXYZ")
    link(nt, tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.0065, 0.0072, 0.009, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.0012, 0.0014, 0.002, 1)
    link(nt, sep.outputs[2], ramp.inputs[0])
    bg = node(nt, "ShaderNodeBackground", Strength=1.0)
    link(nt, ramp.outputs[0], bg.inputs[0])
    link(nt, bg.outputs[0], out.inputs[0])


def area(name, loc, target, energy, color, size):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.color = color
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob


def pillars():
    rnd = random.Random(3)
    m, nt, out = new_mat("M_Preview_Pillar")
    b = node(nt, "ShaderNodeBsdfPrincipled", Roughness=0.7)
    b.inputs["Base Color"].default_value = (0.03, 0.032, 0.036, 1)
    link(nt, b.outputs[0], out.inputs[0])
    for i in range(26):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(13, 26)
        h = rnd.uniform(1.5, 7)
        w = rnd.uniform(0.3, 1.1)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(math.cos(a) * r, math.sin(a) * r - 0.3, h / 2))
        ob = bpy.context.active_object
        ob.scale = (w, w * rnd.uniform(0.6, 1.4), h)
        ob.rotation_euler.z = rnd.uniform(0, 3.14)
        ob.data.materials.append(m)


def compositor(sc, engine):
    """Blender 5.x compositor: bloom, slight chromatic dispersion, vignette."""
    tree = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    sc.compositing_node_group = tree
    N = tree.nodes
    rl = N.new("CompositorNodeRLayers")
    glare = N.new("CompositorNodeGlare")
    for sock, val in (("Type", 'Bloom'), ("Quality", 'High'), ("Threshold", 0.8), ("Strength", 0.55),
                      ("Size", 0.65), ("Saturation", 1.0)):
        try:
            glare.inputs[sock].default_value = val
        except Exception as e:  # noqa: BLE001
            print("glare", sock, e)
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    lens = N.new("CompositorNodeLensdist")
    lens.inputs["Dispersion"].default_value = 0.01
    tree.links.new(glare.outputs["Image"], lens.inputs["Image"])
    ell = N.new("CompositorNodeEllipseMask")
    ell.inputs["Size"].default_value = (0.92, 0.80)
    blur = N.new("CompositorNodeBlur")
    blur.inputs["Size"].default_value = (240, 240)
    tree.links.new(ell.outputs["Mask"], blur.inputs["Image"])
    lift = N.new("ShaderNodeMapRange")
    lift.inputs["To Min"].default_value = 0.45
    tree.links.new(blur.outputs["Image"], lift.inputs["Value"])
    mix = N.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs["Factor"].default_value = 1.0
    tree.links.new(lens.outputs["Image"], mix.inputs[6])
    tree.links.new(lift.outputs["Result"], mix.inputs[7])
    out = N.new("NodeGroupOutput")
    tree.links.new(mix.outputs[2], out.inputs[0])


# ---------------------------------------------------------------------------
class CameraRig:
    def __init__(self, sampler, T, impact_frame, hits):
        self.s, self.T = sampler, T
        cd = bpy.data.cameras.new("PreviewCam")
        cd.lens = 32
        cd.sensor_width = 36
        self.cam = bpy.data.objects.new("PreviewCam", cd)
        bpy.context.scene.collection.objects.link(self.cam)
        bpy.context.scene.camera = self.cam
        self.impact, self.hits = impact_frame, hits
        self.rnd = random.Random(11)
        self.noise = [Vector((self.rnd.gauss(0, 1), self.rnd.gauss(0, 1), self.rnd.gauss(0, 1)))
                      for _ in range(800)]

    def target(self, f):
        acc = Vector((0, 0, 0))
        wsum = 0.0
        for k in range(-24, 25, 2):
            w = math.exp(-(k / 14.0) ** 2)
            h = self.s.at(max(0, min(self.T.end, f + k)))["hips"]
            acc += h * w
            wsum += w
        p = acc / wsum
        accz, wz = 0.0, 0.0
        for k in range(-8, 9):
            w = math.exp(-(k / 5.0) ** 2)
            accz += self.s.at(max(0, min(self.T.end, f + k)))["hips"].z * w
            wz += w
        z = accz / wz
        return Vector((p.x, p.y, 0.62 + (z - 0.8) * 0.85))

    def update(self, f):
        tgt = self.target(f)
        self.last_target = tgt
        # slow orbit: front-right 3/4 -> more profile during the aerial -> back
        u = f / self.T.end
        az = math.radians(-38 - 28 * math.sin(math.pi * min(1.0, u * 1.35)))
        dist = 3.35 - 0.2 * math.sin(math.pi * u)
        off = Vector((math.sin(az), -math.cos(az), 0)) * dist
        loc = tgt + off + Vector((0, 0, 0.42))
        shake = Vector((0, 0, 0))
        for hf, amp in [(self.impact, 0.035)] + [(h, 0.008) for h in self.hits]:
            age = f - hf
            if 0 <= age < 24:
                a = amp * math.exp(-age / 6.0)
                shake += self.noise[(f * 3) % 800] * a
        self.cam.location = loc + shake
        d = (tgt + shake * 0.5) - self.cam.location
        self.cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        age = f - self.impact
        self.cam.data.lens = 32 + (3.0 * math.exp(-age / 10.0) if age >= 0 else 0.0)


# ---------------------------------------------------------------------------
def grid_lines(size=12.0, step=0.5, width=0.008):
    """Thin quads on the floor so contacts / sliding read in solid shading."""
    import bmesh
    bm = bmesh.new()
    n = int(size / step)
    for i in range(-n, n + 1):
        c = i * step
        for (a, b) in (((c - width, -size), (c + width, size)), ((-size, c - width), (size, c + width))):
            v = [bm.verts.new((x, y, 0.001)) for x, y in ((a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1]))]
            bm.faces.new(v)
    me = bpy.data.meshes.new("GridLines")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("GridLines", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def setup_workbench(sc, meshes, sw_obj, floor, trail, shards, ring):
    """Fast solid-shaded preview: studio light, per-object colours,
    transparent trails / ring via object-colour alpha."""
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'OBJECT'
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sh.show_cavity = True
    sh.cavity_type = 'WORLD'
    sh.show_specular_highlight = True
    sh.show_object_outline = False
    sc.display.render_aa = '8'
    sc.world.color = (0.018, 0.020, 0.026)
    sc.render.use_motion_blur = False
    sc.compositing_node_group = None
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    for m in meshes:
        m.color = (0.78, 0.75, 0.72, 1)
    sw_obj.color = (0.96, 0.97, 1.0, 1)
    floor.color = (0.075, 0.080, 0.095, 1)
    grid_lines().color = (0.16, 0.20, 0.25, 1)
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.name.startswith("Cube"):
            ob.color = (0.05, 0.055, 0.065, 1)
    trail.ob.color = (0.65, 0.88, 1.0, 0.38)
    shards.ob.color = (0.75, 0.95, 1.0, 1.0)
    ring.ob.color = (0.7, 0.92, 1.0, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="EEVEE")
    ap.add_argument("--frames", default=None)
    ap.add_argument("--res", default="1280x720")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--blur", type=int, default=1)
    ap.add_argument("--fast", action="store_true", help="playblast quality (workbench only)")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    os.makedirs(args.out, exist_ok=True)

    arm, meshes = su.load_character()
    rig = rigkit.Rig(arm)
    rig.ensure_weapon_bone()
    sw_obj = sword.build_skinned(arm, rig)
    T = combo.build(rig)
    bake.bake(arm, rig, T)

    sc = bpy.context.scene
    rx, ry = (int(v) for v in args.res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.resolution_percentage = 100
    if args.engine.upper().startswith("CYC"):
        sc.render.engine = 'CYCLES'
        sc.cycles.device = 'CPU'
        sc.cycles.samples = args.samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 4
    else:
        sc.render.engine = 'BLENDER_EEVEE'
        ee = sc.eevee
        ee.taa_render_samples = args.samples
        for attr, val in (("use_shadows", True), ("use_raytracing", False), ("shadow_ray_count", 1),
                          ("shadow_step_count", 4)):
            if hasattr(ee, attr):
                setattr(ee, attr, val)
    sc.render.use_motion_blur = bool(args.blur)
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Punchy' if 'AgX - Punchy' in [
        i.identifier for i in sc.view_settings.bl_rna.properties['look'].enum_items] else 'None'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False

    # materials
    cm = character_material()
    for m in meshes:
        m.data.materials.clear()
        m.data.materials.append(cm)
    grp, smats = sword_materials()
    for i, name in enumerate(["M_Sword_Blade", "M_Sword_Guard", "M_Sword_Core", "M_Sword_Grip"]):
        sw_obj.data.materials[i] = smats[name]
    reveal = grp.nodes["reveal"].outputs[0]
    direction = grp.nodes["direction"].outputs[0]

    world_setup()
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    fl = bpy.context.active_object
    fl.data.materials.append(floor_material())
    pillars()
    # lights travel with the action (offset, aim height) so the look stays constant
    kd = bpy.data.lights.new("Key", 'SPOT')
    kd.energy, kd.color, kd.spot_size, kd.spot_blend, kd.shadow_soft_size = 900, (1.0, 0.9, 0.8), 0.95, 0.9, 0.6
    key = bpy.data.objects.new("Key", kd)
    sc.collection.objects.link(key)
    lights = [(key, Vector((1.3, -1.9, 3.4)), 0.7),
              (area("Rim", (0, 0, 0), (0, 0, 1), 520, (0.55, 0.78, 1.0), 1.2), Vector((-1.4, 3.0, 1.6)), 0.9),
              (area("Rim2", (0, 0, 0), (0, 0, 1), 200, (0.75, 0.85, 1.0), 1.0), Vector((2.6, 2.2, 1.0)), 0.9),
              (area("Fill", (0, 0, 0), (0, 0, 1), 16, (0.7, 0.8, 1.0), 4.0), Vector((-3.0, -1.6, 0.4)), 0.7)]

    sampler = fx.SwordSampler(rig, T)
    ev = T.events
    trail = fx.Trail(sampler, fx_material("M_FX_Trail", (0.5, 0.8, 1.0), 1.6, "trail"))
    land = sampler.at(ev["hit_5_impact"])
    tip_land = sampler.point(ev["hit_5_impact"] + 2, fx.BLADE_TIP)
    centre = Vector((tip_land.x, tip_land.y, 0.0))
    shards = fx.Shards(sampler, fx_material("M_FX_Shards", (0.6, 0.92, 1.0), 14.0, "shards"),
                       summon=(ev["summon_start"] - 8, ev["summon_flash"] + 3),
                       dismiss=(ev["dismiss_start"], ev["dismiss_start"] + 22),
                       impact=(ev["hit_5_impact"], centre))
    ring = fx.ImpactRing(fx_material("M_FX_Ring", (0.6, 0.9, 1.0), 6.0, "ring"), ev["hit_5_impact"], centre)
    flash_ld = bpy.data.lights.new("Flash", 'POINT')
    flash_ld.color = (0.6, 0.9, 1.0)
    flash = bpy.data.objects.new("Flash", flash_ld)
    sc.collection.objects.link(flash)
    hits = [ev[k] for k in ev if k.startswith("hit_") and k != "hit_5_impact"]
    camrig = CameraRig(sampler, T, ev["hit_5_impact"], hits)
    workbench = args.engine.upper().startswith("WORK")
    if workbench:
        setup_workbench(sc, meshes, sw_obj, fl, trail, shards, ring)
        if args.fast:
            sc.display.render_aa = 'OFF'
            sc.display.shading.show_shadows = False
            sc.display.shading.show_cavity = False
    else:
        compositor(sc, args.engine)

    # sword dissolve schedule
    s0, s1 = ev["summon_start"], ev["summon_flash"] + 3
    d0, d1 = ev["dismiss_start"], ev["dismiss_start"] + 22

    frames = list(range(0, T.end + 1))
    if args.frames:
        a, rest = args.frames.split("-")
        b, step = (rest.split(":") + ["1"])[:2]
        frames = list(range(int(a), int(b) + 1, int(step)))

    for f in frames:
        sc.frame_set(f)
        if f < d0 - 2:
            u = fx._smooth(s0, s1, f)
            reveal.default_value = -0.25 + 1.5 * u
            direction.default_value = 0.0
        else:
            u = fx._smooth(d0, d1, f)
            reveal.default_value = 1.25 - 1.5 * u
            direction.default_value = 1.0
        trail.update(f)
        shards.update(f)
        ring.update(f)
        if workbench:
            ring.ob.color[3] = 0.85 * ring.ob.get("fade", 0.0)
        camrig.update(f)
        for lob, off, aim_z in lights:
            tgt = camrig.last_target
            lob.location = Vector((tgt.x, tgt.y, 0.0)) + off
            d = Vector((tgt.x, tgt.y, aim_z)) - lob.location
            lob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        # light flashes: sword forming, impact
        e = 0.0
        sp = sampler.at(f)
        pos = sp["M"].translation
        if s0 <= f <= s1 + 8:
            e += 140.0 * fx._smooth(s0, s1, f) * math.exp(-max(0, f - s1) / 3.0)
        age = f - ev["hit_5_impact"]
        if 0 <= age < 25:
            e += 220.0 * math.exp(-age / 3.5)
            pos = centre + Vector((0.0, -0.25, 0.35))
        if d0 <= f <= d1:
            e += 60.0 * math.sin(math.pi * (f - d0) / (d1 - d0))
        flash_ld.energy = e
        flash.location = pos
        sc.render.filepath = os.path.join(args.out, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"frame {f} done", flush=True)


main()
