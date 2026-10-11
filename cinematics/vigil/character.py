"""Character import, shading and a small FK/IK pose solver for the Mixamo rig.

Pose maths
----------
All poses are authored in *armature space* of the imported rig, where

    +X = character's left, +Y = up, +Z = character's forward

Every bone gets a rotation ``Q`` expressed in those (rest-aligned) axes and
applied on top of its parent's accumulated rotation:

    delta[bone] = delta[parent] @ Q[bone]

which lets the choreography say things like "pitch the spine 5 degrees
forward" without caring about each bone's roll. ``Rig.apply`` converts the
deltas into Blender's bone-local quaternions:

    basis = rest_rot^-1 @ Q @ rest_rot
"""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

P = "mixamorig:"

# Armature units are FBX centimetres; the character is 1.25 m tall as shipped,
# we scale her to a 1.70 m adult so the set can be built in real-world metres.
CHAR_HEIGHT_M = 1.70
NATIVE_HEIGHT_U = 125.0
UNIT = CHAR_HEIGHT_M / NATIVE_HEIGHT_U / 1.0  # metres per armature unit (~0.0136)


def qx(deg):
    return Quaternion((1, 0, 0), math.radians(deg))


def qy(deg):
    return Quaternion((0, 1, 0), math.radians(deg))


def qz(deg):
    return Quaternion((0, 0, 1), math.radians(deg))


def frame_rot(a0, b0, a1, b1):
    """Rotation taking the orthonormal frame built from (a0, b0) onto (a1, b1)."""
    a0 = a0.normalized()
    b0 = (b0 - a0 * b0.dot(a0)).normalized()
    a1 = a1.normalized()
    b1 = (b1 - a1 * b1.dot(a1)).normalized()
    m0 = Matrix((a0, b0, a0.cross(b0))).transposed()
    m1 = Matrix((a1, b1, a1.cross(b1))).transposed()
    return (m1 @ m0.transposed()).to_quaternion()


def look_rot(fwd, up=Vector((0, 1, 0))):
    """Rotation turning +Z (forward) to ``fwd`` while keeping +Y as close to ``up``."""
    return frame_rot(Vector((0, 0, 1)), Vector((0, 1, 0)), fwd, up)


# --------------------------------------------------------------------------- import

def _fix_materials(tex_body, tex_face):
    body_img = bpy.data.images.load(tex_body, check_existing=True)
    face_img = bpy.data.images.load(tex_face, check_existing=True)
    for mat_name, img, skin in (("M_c002_body", body_img, False),
                                ("M_c002_head", face_img, True)):
        mat = bpy.data.materials[mat_name]
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Cubic"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        # Dark leather reads glossier than the white cotton: drive roughness
        # from texture luminance.
        lum = nt.nodes.new("ShaderNodeRGBToBW")
        rmap = nt.nodes.new("ShaderNodeMapRange")
        rmap.inputs["From Min"].default_value = 0.0
        rmap.inputs["From Max"].default_value = 0.6
        rmap.inputs["To Min"].default_value = 0.42 if not skin else 0.5
        rmap.inputs["To Max"].default_value = 0.78 if not skin else 0.62
        nt.links.new(tex.outputs["Color"], lum.inputs["Color"])
        nt.links.new(lum.outputs["Val"], rmap.inputs["Value"])
        nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
        bsdf.inputs["Specular IOR Level"].default_value = 0.45
        if skin:
            bsdf.inputs["Subsurface Weight"].default_value = 0.12
            bsdf.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
            bsdf.inputs["Subsurface Scale"].default_value = 0.01
        else:
            bsdf.inputs["Sheen Weight"].default_value = 0.25
            bsdf.inputs["Sheen Roughness"].default_value = 0.4
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])


def import_character(fbx_path, tex_body, tex_face, collection):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    for o in new:
        if o.type == "MESH" and o.parent is None:  # stray Icosphere in the FBX
            bpy.data.objects.remove(o)
            continue
        for c in list(o.users_collection):
            c.objects.unlink(o)
        collection.objects.link(o)
    if arm.animation_data:
        arm.animation_data.action = None
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    _fix_materials(tex_body, tex_face)
    for o in arm.children:
        if o.type == "MESH":
            for p in o.data.polygons:
                p.use_smooth = True
    arm.name = "CHAR_rig"
    s = UNIT
    arm.scale = (s, s, s)
    # Face world +Y (down the nave): armature +Z is forward, +Y is up.
    arm.rotation_mode = "XYZ"
    arm.rotation_euler = (math.radians(90), 0, math.radians(180))
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return arm


# --------------------------------------------------------------------------- solver

class Rig:
    def __init__(self, obj):
        self.obj = obj
        bones = obj.data.bones
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest_rot = {b.name: b.matrix_local.to_quaternion() for b in bones}
        self.head0 = {b.name: b.head_local.copy() for b in bones}
        self.tail0 = {b.name: b.tail_local.copy() for b in bones}
        order, stack = [], [b.name for b in bones if b.parent is None]
        while stack:
            n = stack.pop(0)
            order.append(n)
            stack.extend(c.name for c in bones[n].children)
        self.order = order
        # end/leaf helper bones carry no skin weights - leave them alone
        self.animated = [n for n in order if not n.endswith("_end") and "Top_End" not in n
                         and "Toe_End" not in n and not n.endswith("4")]

    # ---- forward kinematics
    def fk(self, Q, hips_pos):
        delta, head = {}, {}
        for n in self.order:
            p = self.parent[n]
            q = Q.get(n, Quaternion())
            if p is None:
                delta[n] = q
                head[n] = hips_pos.copy()
            else:
                delta[n] = delta[p] @ q
                head[n] = head[p] + delta[p] @ (self.head0[n] - self.head0[p])
        return delta, head

    def bone_len(self, a, b):
        return (self.head0[b] - self.head0[a]).length

    # ---- analytic two-bone IK
    def two_bone(self, Q, delta, head, upper, lower, end, target, pole, ref_perp,
                 end_delta=None, stretch=0.9995):
        """Solve upper/lower so that ``end``'s head reaches ``target``.

        ``pole`` is the direction the middle joint should point; ``ref_perp`` is
        the direction that joint would bend towards in the rest pose. Writes the
        resulting Q's into ``Q`` and returns the achieved end position.
        """
        u0 = self.head0[lower] - self.head0[upper]
        l0 = self.head0[end] - self.head0[lower]
        L1, L2 = u0.length, l0.length
        root = head[upper]
        d = target - root
        dist = d.length
        reach = (L1 + L2) * stretch
        dirv = d.normalized()
        if dist > reach:
            dist = reach
        dist = max(dist, abs(L1 - L2) + 1e-3)
        cos_a = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
        a = math.acos(max(-1.0, min(1.0, cos_a)))
        n = pole - dirv * pole.dot(dirv)
        if n.length < 1e-6:
            n = ref_perp - dirv * ref_perp.dot(dirv)
        n.normalize()
        mid = root + dirv * (L1 * math.cos(a)) + n * (L1 * math.sin(a))
        tip = root + dirv * dist
        d_up = frame_rot(u0, ref_perp, mid - root, n)
        d_lo = frame_rot(l0, ref_perp, tip - mid, n)
        parent_delta = delta[self.parent[upper]]
        Q[upper] = parent_delta.inverted() @ d_up
        Q[lower] = d_up.inverted() @ d_lo
        if end_delta is not None:
            Q[end] = d_lo.inverted() @ end_delta
        return tip

    # ---- write keys
    def apply(self, Q, hips_pos, frame=None):
        pose = self.obj.pose.bones
        for n in self.animated:
            pb = pose[n]
            r = self.rest_rot[n]
            q = r.inverted() @ Q.get(n, Quaternion()) @ r
            q.normalize()
            pb.rotation_quaternion = q
            if frame is not None:
                pb.keyframe_insert("rotation_quaternion", frame=frame, group=n)
        hips = P + "Hips"
        pose[hips].location = self.rest_rot[hips].to_matrix().inverted() @ (hips_pos - self.head0[hips])
        if frame is not None:
            pose[hips].keyframe_insert("location", frame=frame, group=hips)
