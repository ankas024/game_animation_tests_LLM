"""Lighting, cameras, edit and render settings for VIGIL."""

import math

import bmesh
import bpy
from mathutils import Vector, kdtree

import materials as M
from character import P
from performance import FPS, Curve, mix, smooth, wobble

# (name, first frame, last frame)
SHOTS = [
    ("01_doorway", 1, 130),
    ("02_boots", 131, 200),
    ("03_walk_front", 201, 350),
    ("04_look_up", 351, 480),
    ("05_face", 481, 620),
    ("06_hand", 621, 668),
    ("07_glow", 669, 770),
    ("08_wide", 771, 840),
]
FRAME_END = SHOTS[-1][2]
# deformation motion blur only where things move fast enough to need it
MOTION_BLUR_SHOTS = {"01_doorway", "02_boots", "03_walk_front", "06_hand"}


def shot_at(frame):
    return next(name for name, f0, f1 in SHOTS if f0 <= frame <= f1)


def _obj(name, data, col):
    o = bpy.data.objects.new(name, data)
    col.objects.link(o)
    return o


def aim(obj, target):
    d = Vector(target) - obj.location
    # stay continuous with the previous key: a +-180 deg yaw wrap would make motion blur
    # interpolate through a full spin between frames
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler("XYZ", obj.rotation_euler)


def key_energy(light, curve, f0, f1, step=1):
    for f in range(f0, f1 + 1, step):
        light.energy = curve(f)
        light.keyframe_insert("energy", frame=f)


class Cinematography:
    def __init__(self, perf, env, arm):
        self.perf = perf
        self.env = env
        self.arm = arm
        self.col = bpy.data.collections.new("CINE")
        bpy.context.scene.collection.children.link(self.col)
        self.stop = Vector((0.0, perf.stop_world_y, 0.0))
        self.hole = env.info["hole"]
        self.beam_dir = env.info["beam_dir"]

    def build(self):
        self.world()
        self.lights()
        self.cam_path = []
        self.cameras()
        self._clear_motes_near_cameras()
        return self

    def _clear_motes_near_cameras(self, radius=1.3):
        """Dust right in front of a lens turns into giant bokeh blobs: keep it out of camera paths."""
        me = self.env.motes_obj.data
        kd = kdtree.KDTree(len(self.cam_path))
        for i, p in enumerate(self.cam_path):
            kd.insert(p, i)
        kd.balance()
        bm = bmesh.new()
        bm.from_mesh(me)
        doomed = [v for v in bm.verts if kd.find(v.co)[2] < radius]
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
        bm.to_mesh(me)
        bm.free()

    # ------------------------------------------------------------------ world
    def world(self):
        w = bpy.data.worlds.new("night")
        bpy.context.scene.world = w
        nt = w.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputWorld")
        bg = nt.nodes.new("ShaderNodeBackground")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        grad = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sep.outputs["Z"], grad.inputs["Value"])
        grad.inputs["From Min"].default_value = -0.1
        grad.inputs["From Max"].default_value = 0.8
        mixn = nt.nodes.new("ShaderNodeMix")
        mixn.data_type = "RGBA"
        nt.links.new(grad.outputs["Result"], mixn.inputs[0])
        mixn.inputs[6].default_value = (0.012, 0.018, 0.035, 1)
        mixn.inputs[7].default_value = (0.0015, 0.0025, 0.006, 1)
        # stars
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 420.0
        nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
        st = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(vor.outputs["Distance"], st.inputs["Value"])
        st.inputs["From Min"].default_value = 0.06
        st.inputs["From Max"].default_value = 0.0
        st.inputs["To Max"].default_value = 3.0
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        add.inputs[0].default_value = 1.0
        nt.links.new(mixn.outputs[2], add.inputs[6])
        nt.links.new(st.outputs["Result"], add.inputs[7])
        nt.links.new(add.outputs[2], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 1.0
        nt.links.new(bg.outputs[0], out.inputs["Surface"])
        # the moon, sitting exactly up the grace beam so it shows through the hole
        moon_pos = self.stop + self.beam_dir * 700.0
        bpy.ops.mesh.primitive_uv_sphere_add(radius=9.0, location=moon_pos, segments=32, ring_count=16)
        moon = bpy.context.active_object
        for c in list(moon.users_collection):
            c.objects.unlink(moon)
        self.col.objects.link(moon)
        moon.name = "moon"
        moon.data.materials.append(M.emissive("M_moon", (0.82, 0.88, 1.0), 40.0))
        moon.visible_shadow = False
        moon.visible_diffuse = False

    # ------------------------------------------------------------------ lights
    def lights(self):
        col = self.col
        # moon through the side windows (cinematic cheat: a different angle from the beam)
        sun = bpy.data.lights.new("moon_sun", "SUN")
        sun.energy = 5.0
        sun.color = (0.55, 0.68, 1.0)
        sun.angle = math.radians(0.8)
        so = _obj("moon_sun", sun, col)
        az, el = math.radians(68), math.radians(36)
        travel = -Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))
        so.rotation_euler = travel.to_track_quat("-Z", "Y").to_euler()

        # the grace beam: a far, tight spot pouring through the broken vault
        sp = bpy.data.lights.new("grace_beam", "SPOT")
        dist = 120.0
        sp.spot_size = 2 * math.atan(2.1 / dist)
        sp.spot_blend = 0.3
        sp.shadow_soft_size = 0.6
        sp.color = (0.74, 0.84, 1.0)
        self.beam_base = 13.0 * 4 * math.pi * dist * dist  # ~13 W/m2 on the floor
        spo = _obj("grace_beam", sp, col)
        spo.location = self.stop + self.beam_dir * dist
        aim(spo, self.stop)
        beam = Curve([(1, 1.0), (430, 1.0), (470, 1.25), (566, 1.3), (626, 1.9), (645, 2.8),
                      (668, 0.35), (700, 0.2), (840, 0.16)])
        key_energy(sp, lambda f: self.beam_base * beam(f), 1, FRAME_END, 2)

        # light pouring in through the west door
        dl = bpy.data.lights.new("door_light", "AREA")
        dl.shape = "RECTANGLE"
        dl.size, dl.size_y = 5.0, 6.0
        dl.energy = 1500.0
        dl.color = (0.62, 0.74, 1.0)
        do = _obj("door_light", dl, col)
        do.location = (0.0, -30.0, 4.5)
        aim(do, (0.0, -12.0, 0.0))
        do.visible_camera = False

        # rose window glow spilling into the sanctuary
        rl = bpy.data.lights.new("rose_light", "AREA")
        rl.shape = "DISK"
        rl.size = 7.0
        rl.energy = 500.0
        rl.spread = math.radians(70)
        rl.color = (0.75, 0.35, 0.6)
        ro = _obj("rose_light", rl, col)
        ro.location = (0.0, 23.3, 13.8)
        aim(ro, (0.0, 0.0, 2.0))
        ro.visible_camera = False
        ro.visible_glossy = False

        # light caught in her fist
        gl = bpy.data.lights.new("fist_glow", "POINT")
        gl.color = (0.72, 0.86, 1.0)
        gl.shadow_soft_size = 0.02
        go = _obj("fist_glow", gl, col)
        self._attach_to_palm(go)
        glow = Curve([(636, 0.0), (650, 1.6), (668, 1.0), (840, 1.0)])

        def glow_w(f):
            g = glow(f)
            return 9.0 * g * (1.0 + 0.12 * math.sin(f * 0.21) + 0.06 * math.sin(f * 0.57))

        key_energy(gl, glow_w, 600, FRAME_END)
        # a tiny emissive core so the leak between fingers blooms
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.1, segments=16, ring_count=8)
        core = bpy.context.active_object
        for c in list(core.users_collection):
            c.objects.unlink(core)
        col.objects.link(core)
        core.name = "fist_core"
        mat = M.emissive("M_core", (0.75, 0.88, 1.0), 0.0)
        core.data.materials.append(mat)
        em = mat.node_tree.nodes["Emission"]
        for f in range(600, FRAME_END + 1, 2):
            em.inputs["Strength"].default_value = 40.0 * glow(f)
            em.inputs["Strength"].keyframe_insert("default_value", frame=f)
        core.visible_shadow = False
        self._attach_to_palm(core)

        # soft fill that rides with the camera on character shots
        fl = bpy.data.lights.new("face_fill", "AREA")
        fl.shape = "DISK"
        fl.size = 1.2
        fl.color = (0.7, 0.8, 1.0)
        self.fill = _obj("face_fill", fl, col)
        self.fill.visible_camera = False
        self.fill.visible_glossy = False

        # motes swirl when the light is caught
        node = self.env.motes_obj.modifiers["drift"].node_group.nodes["mote_amp"]
        swirl = Curve([(600, 1.6), (640, 2.1), (700, 1.7)])
        for f in range(590, 720, 5):
            node.inputs["Scale"].default_value = swirl(f)
            node.inputs["Scale"].keyframe_insert("default_value", frame=f)

    def _attach_to_palm(self, obj):
        rig = self.arm
        hand = rig.data.bones[P + "RightHand"]
        mid = rig.data.bones[P + "RightHandMiddle1"].head_local
        # palm centre: halfway to the knuckles, a little toward the palm (-Y in rest pose)
        target = hand.head_local.lerp(mid, 0.55) + Vector((0, -2.2, 0))
        local = hand.matrix_local.inverted() @ target
        obj.parent = rig
        obj.parent_type = "BONE"
        obj.parent_bone = hand.name
        obj.location = local - Vector((0, hand.length, 0))
        obj.scale = (1, 1, 1)

    # ------------------------------------------------------------------ cameras
    def _cam(self, name, lens, fstop):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36.0
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 7
        cd.clip_start = 0.05
        cd.clip_end = 2000
        return _obj(name, cd, self.col)

    def _key_cam(self, cam, f, loc, target, focus, shake=0.0, roll=0.0):
        cam.location = loc
        aim(cam, target)
        e = cam.rotation_euler
        e.x += math.radians(wobble(f, 1.1 + sum(map(ord, cam.name)) % 7, 4.0, shake))
        e.z += math.radians(wobble(f, 3.7 + sum(map(ord, cam.name)) % 5, 5.0, shake))
        e.y += math.radians(roll)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        self.cam_path.append(Vector(loc))
        cam.data.dof.focus_distance = max(0.1, (Vector(focus) - Vector(loc)).length)
        cam.data.dof.keyframe_insert("focus_distance", frame=f)

    def _fill(self, f, loc, target, energy):
        self.fill.location = loc
        aim(self.fill, target)
        self.fill.data.energy = energy
        self.fill.keyframe_insert("location", frame=f)
        self.fill.keyframe_insert("rotation_euler", frame=f)
        self.fill.data.keyframe_insert("energy", frame=f)

    def cameras(self):
        sc = bpy.context.scene
        tr = self.perf.track
        stop_y = self.stop.y
        sc.timeline_markers.clear()
        cams = {}
        for name, f0, f1 in SHOTS:
            cams[name] = c = self._cam("CAM_" + name, 35, 2.8)
            m = sc.timeline_markers.new(name, frame=f0)
            m.camera = c
        sc.camera = cams[SHOTS[0][0]]

        def V(*a):
            return Vector(a)

        # 01 doorway: low in the nave, she is a silhouette in the door, then walks toward us
        c = cams["01_doorway"]
        c.data.lens = 30
        c.data.dof.aperture_fstop = 11.0
        for f in range(1, 131):
            u = smooth((f - 1) / 129)
            loc = V(-0.55, mix(-11.4, -12.4, u), mix(0.8, 1.0, u))
            hips = tr[f]["hips"]
            tgt = V(0.0, -21.0, 2.0).lerp(V(hips.x, hips.y, 1.45), smooth((f - 40) / 90) * 0.75)
            self._key_cam(c, f, loc, tgt, hips, shake=0.12)
            self._fill(f, V(0, -30, 0), V(0, 0, 0), 0.0)

        # 02 boots: ankle-height tracking from her right
        c = cams["02_boots"]
        c.data.lens = 45
        c.data.dof.aperture_fstop = 2.8
        for f in range(131, 201):
            hips = tr[f]["hips"]
            feet = (tr[f]["lfoot"] + tr[f]["rfoot"]) / 2
            loc = V(1.35, hips.y + 0.55, 0.2)
            self._key_cam(c, f, loc, V(0.0, hips.y - 0.15, 0.2), feet, shake=0.25)

        # 03 walking toward camera, long lens, shallow focus
        c = cams["03_walk_front"]
        c.data.lens = 70
        c.data.dof.aperture_fstop = 2.5
        for f in range(201, 351):
            hips, head = tr[f]["hips"], tr[f]["head"]
            u = smooth((f - 201) / 149)
            loc = V(mix(0.35, 0.15, u), hips.y + mix(3.1, 2.6, u), 1.28)
            tgt = V(head.x * 0.6, head.y, mix(1.38, 1.46, u))
            self._key_cam(c, f, loc, tgt, head, shake=0.18)
            self._fill(f, loc + V(-0.6, 0.0, 0.5), head, 55.0)

        # 04 behind her as she stops in the beam; tilt up with her gaze to the broken vault
        c = cams["04_look_up"]
        c.data.lens = 15
        c.data.dof.aperture_fstop = 5.6
        for f in range(351, 481):
            hips = tr[f]["hips"]
            u = smooth((f - 351) / 129)
            loc = V(mix(-0.8, -1.1, u), min(hips.y, stop_y) - mix(3.4, 4.2, u), mix(0.7, 0.45, u))
            look = smooth((f - 420) / 60)
            tgt = V(hips.x, hips.y + 3.0, 1.6).lerp(V(0.5, stop_y + 6.0, 7.2), look)
            self._key_cam(c, f, loc, tgt, hips, shake=0.1)
            self._fill(f, V(0, -30, 0), V(0, 0, 0), 0.0)

        # 05 her face in the moonbeam; the hand rises into frame, focus racks to it
        c = cams["05_face"]
        c.data.lens = 40
        c.data.dof.aperture_fstop = 3.2
        rack = Curve([(540, 0.0), (566, 1.0)])
        tilt = Curve([(515, 0.0), (575, 0.5)])
        for f in range(481, 621):
            head, hand = tr[f]["head"], tr[f]["rhand"]
            u = smooth((f - 481) / 139)
            loc = V(mix(0.75, 0.68, u), stop_y + mix(1.45, 1.3, u), mix(1.05, 0.98, u))
            tgt = head.lerp(hand, tilt(f)) + V(0, 0, 0.12)
            focus = head.lerp(hand, rack(f))
            self._key_cam(c, f, loc, tgt, focus, shake=0.1)
            self._fill(f, loc + V(0.5, 0.2, -0.3), head, 18.0)

        # 06 insert: the hand against the beam, closing - then dropping to her heart
        c = cams["06_hand"]
        c.data.lens = 42
        c.data.dof.aperture_fstop = 2.2
        h0 = tr[628]["rhand"]
        for f in range(621, 669):
            hand = tr[f]["rhand"]
            u = smooth((f - 621) / 47)
            loc = h0 + V(0.75, -0.95, mix(-0.62, -0.75, u))
            tgt = h0.lerp(hand, 0.65) + V(0, 0, 0.04)
            self._key_cam(c, f, loc, tgt, hand, shake=0.12)
            self._fill(f, V(0, -30, 0), V(0, 0, 0), 0.0)

        # 07 the light held at her chest lights her face from below
        c = cams["07_glow"]
        c.data.lens = 55
        c.data.dof.aperture_fstop = 2.8
        for f in range(669, 771):
            head, chest = tr[f]["head"], tr[f]["rhand"]
            u = smooth((f - 669) / 101)
            loc = V(mix(-0.55, -0.42, u), stop_y + mix(1.75, 1.45, u), mix(1.02, 1.08, u))
            tgt = chest.lerp(head, 0.62)
            self._key_cam(c, f, loc, tgt, head, shake=0.1)
            self._fill(f, loc + V(-0.4, 0.3, 0.4), head, 6.0)

        # 08 rising pull-back: alone in the nave, the last light in her hand, the rose window ahead
        c = cams["08_wide"]
        c.data.lens = 18
        c.data.dof.aperture_fstop = 8.0
        rose = self.env.rose_c
        for f in range(771, 841):
            u = (f - 771) / 69
            u = u * u * (3 - 2 * u) * 0.6 + u * 0.4
            loc = V(mix(0.3, 0.05, u), stop_y - mix(3.0, 7.5, u), mix(1.4, 2.8, u))
            chest = tr[f]["chest"]
            aim_dir = (chest - loc).normalized() * 0.56 + (rose - loc).normalized() * 0.44
            self._key_cam(c, f, loc, loc + aim_dir, tr[f]["hips"], shake=0.05)
            self._fill(f, V(0, -30, 0), V(0, 0, 0), 0.0)


# ---------------------------------------------------------------------- render setup

def render_settings(res_x=1920, res_y=804, samples=64, motion_blur=True):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.05
    cy.adaptive_min_samples = 8
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    cy.denoising_prefilter = "ACCURATE"
    cy.use_light_tree = False   # ~17 lights: the tree costs more than it saves here
    cy.max_bounces = 6
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 2
    cy.transmission_bounces = 2
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 8
    cy.sample_clamp_indirect = 4.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.volume_step_rate = 2.0
    sc.render.use_persistent_data = True
    sc.render.resolution_x = res_x
    sc.render.resolution_y = res_y
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.frame_start = 1
    sc.frame_end = FRAME_END
    sc.render.use_motion_blur = motion_blur
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.film_transparent = False


def compositor(bloom=0.35):
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("VIGIL_comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Quality"].default_value = "High"
    gl.inputs["Threshold"].default_value = 0.9
    gl.inputs["Smoothness"].default_value = 0.4
    gl.inputs["Strength"].default_value = bloom
    gl.inputs["Size"].default_value = 0.75
    ld = ng.nodes.new("CompositorNodeLensdist")
    ld.inputs["Distortion"].default_value = -0.008
    ld.inputs["Dispersion"].default_value = 0.012
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], ld.inputs["Image"])
    ng.links.new(ld.outputs["Image"], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    sc.render.compositor_device = "CPU"
    sc.render.compositor_precision = "FULL"
