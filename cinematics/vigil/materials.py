"""Procedural (texture-free) materials for the cathedral set."""

import bpy


def _sock(sockets, ident):
    return next(s for s in sockets if s.identifier == ident)


class NB:
    """Tiny node-building helper around a material's node tree."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, kind, **inputs):
        node = self.nt.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 200
        for k, v in inputs.items():
            if k in node.inputs.keys():
                self.set(node.inputs[k], v)
            else:
                setattr(node, k, v)
        return node

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        else:
            sock.default_value = v

    def link(self, a, b):
        self.nt.links.new(a, b)

    def mix(self, fac, a, b, blend="MIX"):
        m = self.nt.nodes.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = blend
        self.set(_sock(m.inputs, "Factor_Float"), fac)
        self.set(_sock(m.inputs, "A_Color"), a)
        self.set(_sock(m.inputs, "B_Color"), b)
        return _sock(m.outputs, "Result_Color")

    def mixf(self, fac, a, b):
        m = self.nt.nodes.new("ShaderNodeMix")
        m.data_type = "FLOAT"
        self.set(_sock(m.inputs, "Factor_Float"), fac)
        self.set(_sock(m.inputs, "A_Float"), a)
        self.set(_sock(m.inputs, "B_Float"), b)
        return _sock(m.outputs, "Result_Float")

    def maprange(self, v, a, b, c, d, clamp=True, interp="LINEAR"):
        m = self.n("ShaderNodeMapRange", interpolation_type=interp)
        m.clamp = clamp
        self.set(m.inputs["Value"], v)
        m.inputs["From Min"].default_value = a
        m.inputs["From Max"].default_value = b
        m.inputs["To Min"].default_value = c
        m.inputs["To Max"].default_value = d
        return m.outputs["Result"]

    def math(self, op, a, b=0.0):
        m = self.n("ShaderNodeMath", operation=op)
        self.set(m.inputs[0], a)
        self.set(m.inputs[1], b)
        return m.outputs[0]

    def out(self, shader, volume=None):
        o = self.n("ShaderNodeOutputMaterial")
        if shader is not None:
            self.link(shader, o.inputs["Surface"])
        if volume is not None:
            self.link(volume, o.inputs["Volume"])
        return o


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m, NB(m)


def stone(name="M_stone", tint=(1.0, 1.0, 1.0), blocks=True, scale=1.0):
    m, b = new_mat(name)
    geo = b.n("ShaderNodeNewGeometry")
    sep = b.n("ShaderNodeSeparateXYZ", Vector=geo.outputs["Position"])
    # wall-aligned 2D coordinates: (x + y) runs along any axis-aligned wall
    along = b.math("ADD", sep.outputs["X"], sep.outputs["Y"])
    uv = b.n("ShaderNodeCombineXYZ", X=along, Y=sep.outputs["Z"])
    t = tint
    c1 = (0.30 * t[0], 0.285 * t[1], 0.265 * t[2], 1)
    c2 = (0.22 * t[0], 0.21 * t[1], 0.20 * t[2], 1)
    noise = b.n("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=1.6 * scale, Detail=3.0,
                Roughness=0.6)
    base = b.mix(noise.outputs["Fac"], c2, c1)
    if blocks:
        brick = b.n("ShaderNodeTexBrick", Vector=uv.outputs["Vector"], Scale=1.0, **{
            "Mortar Size": 0.015, "Mortar Smooth": 0.3, "Bias": 0.0, "Brick Width": 0.92,
            "Row Height": 0.41})
        brick.offset = 0.5
        b.set(brick.inputs["Color1"], (1, 1, 1, 1))
        b.set(brick.inputs["Color2"], (0.72, 0.70, 0.68, 1))
        b.set(brick.inputs["Mortar"], (0.35, 0.34, 0.33, 1))
        base = b.mix(1.0, base, brick.outputs["Color"], "MULTIPLY")
        groove = brick.outputs["Fac"]
    # damp streaks running down the walls + darker, greener base near the floor
    streak_vec = b.n("ShaderNodeMapping", Vector=geo.outputs["Position"])
    streak_vec.inputs["Scale"].default_value = (1.0, 1.0, 0.12)
    streak = b.n("ShaderNodeTexNoise", Vector=streak_vec.outputs["Vector"], Scale=3.0, Detail=3.0)
    streak_m = b.maprange(streak.outputs["Fac"], 0.45, 0.7, 0.0, 0.55)
    base = b.mix(streak_m, base, (0.06, 0.06, 0.055, 1))
    low = b.maprange(sep.outputs["Z"], 0.0, 1.6, 1.0, 0.0)
    base = b.mix(b.math("MULTIPLY", low, 0.6), base, (0.07, 0.085, 0.06, 1))
    rough = b.maprange(streak.outputs["Fac"], 0.4, 0.7, 0.88, 0.55)
    detail = b.n("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=14.0 * scale, Detail=3.0)
    bump = b.n("ShaderNodeBump", Strength=0.35, Distance=0.02, Height=detail.outputs["Fac"])
    if blocks:
        bump2 = b.n("ShaderNodeBump", Strength=0.6, Distance=0.03, Height=groove,
                    Normal=bump.outputs["Normal"])
        nrm = bump2.outputs["Normal"]
    else:
        nrm = bump.outputs["Normal"]
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": base, "Roughness": rough, "Normal": nrm})
    b.out(bsdf.outputs["BSDF"])
    return m


def floor(name="M_floor"):
    m, b = new_mat(name)
    geo = b.n("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    brick = b.n("ShaderNodeTexBrick", Vector=pos, Scale=1.0, **{
        "Mortar Size": 0.018, "Mortar Smooth": 0.2, "Bias": 0.1, "Brick Width": 1.25, "Row Height": 0.85})
    brick.offset = 0.37
    b.set(brick.inputs["Color1"], (0.20, 0.19, 0.18, 1))
    b.set(brick.inputs["Color2"], (0.13, 0.125, 0.12, 1))
    b.set(brick.inputs["Mortar"], (0.04, 0.04, 0.04, 1))
    wear = b.n("ShaderNodeTexNoise", Vector=pos, Scale=2.5, Detail=3.0, Roughness=0.65)
    base = b.mix(b.maprange(wear.outputs["Fac"], 0.3, 0.7, 0.0, 0.5), brick.outputs["Color"],
                 (0.30, 0.28, 0.26, 1))
    # puddles: low-frequency noise threshold
    pud_n = b.n("ShaderNodeTexNoise", Vector=pos, Scale=0.32, Detail=3.0, Roughness=0.5)
    pud = b.maprange(pud_n.outputs["Fac"], 0.54, 0.58, 0.0, 1.0)
    # mortar gaps stay wet too
    wet_mortar = b.math("MULTIPLY", brick.outputs["Fac"], 0.8)
    wet = b.math("MAXIMUM", pud, wet_mortar)
    base = b.mix(wet, base, (0.035, 0.035, 0.038, 1))
    rough = b.mixf(wet, b.maprange(wear.outputs["Fac"], 0.3, 0.7, 0.42, 0.75), 0.03)
    detail = b.n("ShaderNodeTexNoise", Vector=pos, Scale=18.0, Detail=3.0)
    hgt = b.math("ADD", brick.outputs["Fac"], b.math("MULTIPLY", detail.outputs["Fac"], 0.15))
    hgt = b.math("MULTIPLY", hgt, b.math("SUBTRACT", 1.0, pud))
    bump = b.n("ShaderNodeBump", Strength=0.5, Distance=0.02, Height=hgt)
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": base, "Roughness": rough,
                                              "Normal": bump.outputs["Normal"]})
    b.out(bsdf.outputs["BSDF"])
    return m


def wood(name="M_wood"):
    m, b = new_mat(name)
    tc = b.n("ShaderNodeTexCoord")
    mp = b.n("ShaderNodeMapping", Vector=tc.outputs["Object"])
    mp.inputs["Scale"].default_value = (1.0, 6.0, 6.0)
    wave = b.n("ShaderNodeTexWave", Vector=mp.outputs["Vector"], Scale=2.0, Distortion=6.0, Detail=3.0)
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    base = b.mix(b.maprange(wave.outputs["Fac"], 0.2, 0.9, 0.0, 1.0), (0.05, 0.028, 0.016, 1),
                 (0.11, 0.065, 0.035, 1))
    grime = b.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=3.0, Detail=3.0)
    base = b.mix(b.maprange(grime.outputs["Fac"], 0.45, 0.7, 0.0, 0.6), base, (0.03, 0.03, 0.03, 1))
    bump = b.n("ShaderNodeBump", Strength=0.25, Distance=0.01, Height=wave.outputs["Fac"])
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": base, "Roughness": 0.62,
                                              "Normal": bump.outputs["Normal"]})
    b.out(bsdf.outputs["BSDF"])
    return m


def iron(name="M_iron"):
    m, b = new_mat(name)
    tc = b.n("ShaderNodeTexCoord")
    rust = b.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=8.0, Detail=3.0)
    col = b.mix(b.maprange(rust.outputs["Fac"], 0.5, 0.75, 0.0, 1.0), (0.04, 0.04, 0.045, 1),
                (0.09, 0.04, 0.02, 1))
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Metallic": 0.8,
                                              "Roughness": b.maprange(rust.outputs["Fac"], 0.5, 0.75, 0.45, 0.85)})
    b.out(bsdf.outputs["BSDF"])
    return m


def stained_glass(name="M_glass_rose", strength=3.0):
    m, b = new_mat(name)
    tc = b.n("ShaderNodeTexCoord")
    vor = b.n("ShaderNodeTexVoronoi", Vector=tc.outputs["Object"], Scale=2.6)
    vor.voronoi_dimensions = "3D"
    ramp = b.n("ShaderNodeValToRGB")
    b.link(b.n("ShaderNodeRGBToBW", Color=vor.outputs["Color"]).outputs["Val"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    palette = [(0.0, (0.02, 0.05, 0.55)), (0.22, (0.55, 0.02, 0.05)), (0.38, (0.03, 0.18, 0.6)),
               (0.5, (0.85, 0.42, 0.05)), (0.62, (0.25, 0.03, 0.45)), (0.75, (0.03, 0.35, 0.3)),
               (0.88, (0.6, 0.05, 0.08))]
    cr.elements[0].position, cr.elements[0].color = palette[0][0], palette[0][1] + (1,)
    cr.elements[1].position, cr.elements[1].color = palette[1][0], palette[1][1] + (1,)
    for p, c in palette[2:]:
        e = cr.elements.new(p)
        e.color = c + (1,)
    edge = b.n("ShaderNodeTexVoronoi", Vector=tc.outputs["Object"], Scale=2.6)
    edge.feature = "DISTANCE_TO_EDGE"
    lead = b.maprange(edge.outputs["Distance"], 0.02, 0.05, 0.0, 1.0)
    grain = b.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=30.0, Detail=3.0)
    lum = b.math("MULTIPLY", lead, b.maprange(grain.outputs["Fac"], 0.3, 0.7, 0.6, 1.2))
    em = b.n("ShaderNodeEmission", Color=ramp.outputs["Color"],
             Strength=b.math("MULTIPLY", lum, strength))
    b.out(em.outputs["Emission"])
    return m


def emissive(name, color, strength):
    m, b = new_mat(name)
    em = b.n("ShaderNodeEmission", Color=tuple(color) + (1,), Strength=strength)
    b.out(em.outputs["Emission"])
    return m


def flame(name="M_flame"):
    m, b = new_mat(name)
    tc = b.n("ShaderNodeTexCoord")
    sep = b.n("ShaderNodeSeparateXYZ", Vector=tc.outputs["Generated"])
    # hotter, whiter core at the base of the flame
    col = b.mix(b.maprange(sep.outputs["Z"], 0.0, 0.7, 0.0, 1.0), (1.0, 0.75, 0.42, 1), (1.0, 0.36, 0.06, 1))
    em = b.n("ShaderNodeEmission", Color=col, Strength=b.maprange(sep.outputs["Z"], 0.0, 1.0, 60.0, 18.0))
    b.out(em.outputs["Emission"])
    return m


def wax(name="M_wax"):
    m, b = new_mat(name)
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": (0.8, 0.72, 0.58, 1), "Roughness": 0.45,
                                              "Subsurface Weight": 0.6, "Subsurface Scale": 0.02})
    b.out(bsdf.outputs["BSDF"])
    return m


def banner(name="M_banner"):
    m, b = new_mat(name)
    tc = b.n("ShaderNodeTexCoord")
    sep = b.n("ShaderNodeSeparateXYZ", Vector=tc.outputs["UV"])
    trim = b.math("MAXIMUM", b.maprange(sep.outputs["X"], 0.06, 0.08, 1.0, 0.0),
                  b.maprange(sep.outputs["X"], 0.92, 0.94, 0.0, 1.0))
    col = b.mix(trim, (0.16, 0.008, 0.012, 1), (0.42, 0.28, 0.07, 1))
    # tattered hem: noise eats into the bottom of the cloth
    tat = b.n("ShaderNodeTexNoise", Vector=tc.outputs["UV"], Scale=9.0, Detail=3.0)
    hem = b.math("ADD", sep.outputs["Y"], b.math("MULTIPLY", tat.outputs["Fac"], 0.28))
    alpha = b.maprange(hem, 0.22, 0.24, 0.0, 1.0)
    holes = b.maprange(tat.outputs["Fac"], 0.72, 0.74, 1.0, 0.0)
    alpha = b.math("MULTIPLY", alpha, holes)
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.8, "Sheen Weight": 0.8,
                                              "Sheen Roughness": 0.35, "Alpha": alpha,
                                              "Metallic": b.math("MULTIPLY", trim, 0.6)})
    b.out(bsdf.outputs["BSDF"])
    return m


def fog(name="M_fog", density=0.02, anisotropy=0.6, color=(0.86, 0.9, 1.0), emission=0.0,
        emission_color=(0.5, 0.6, 0.8)):
    m, b = new_mat(name)
    vol = b.n("ShaderNodeVolumePrincipled", Color=tuple(color) + (1,), Density=density,
              Anisotropy=anisotropy)
    if emission:
        vol.inputs["Emission Strength"].default_value = emission
        vol.inputs["Emission Color"].default_value = tuple(emission_color) + (1,)
    b.out(None, vol.outputs["Volume"])
    return m


def mote(name="M_mote"):
    m, b = new_mat(name)
    bsdf = b.n("ShaderNodeBsdfPrincipled", **{"Base Color": (0.9, 0.9, 0.85, 1), "Roughness": 0.4,
                                              "Emission Color": (0.7, 0.8, 1.0, 1),
                                              "Emission Strength": 0.03})
    b.out(bsdf.outputs["BSDF"])
    return m
