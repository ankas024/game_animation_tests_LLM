"""Clay preview renders for build_dodge_anims.py (Cycles CPU, no GPU needed).

Writes <out>/<clip>.gif and <out>/<clip>_sheet.jpg (every other frame).
"""
import os

import bpy
from mathutils import Vector

RES_X, RES_Y = 640, 360


def _setup(arm):
    sc = bpy.context.scene
    if "preview_cam" in bpy.data.objects:
        return sc
    for o in bpy.data.objects:
        if o.type == "MESH" and o.parent is not arm:
            o.hide_render = True

    clay = bpy.data.materials.new("clay")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.6, 0.57, 1)
    bsdf.inputs["Roughness"].default_value = 0.55
    for o in arm.children:
        if o.type == "MESH":
            for i in range(len(o.material_slots)):
                o.material_slots[i].link = "OBJECT"
                o.material_slots[i].material = clay

    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    floor = bpy.context.active_object
    fm = bpy.data.materials.new("floor")
    fm.use_nodes = True
    nt = fm.node_tree
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 60
    chk.inputs["Color1"].default_value = (0.32, 0.33, 0.36, 1)
    chk.inputs["Color2"].default_value = (0.24, 0.25, 0.28, 1)
    nt.links.new(chk.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    floor.data.materials.append(fm)

    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.5
    sun.angle = 0.08
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (0.65, 0.25, 0.5)
    if sc.world is None:
        sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.44, 0.5, 1)
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6

    cam = bpy.data.cameras.new("preview_cam")
    cam.lens = 35
    co = bpy.data.objects.new("preview_cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 12
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
    sc.render.image_settings.file_format = "PNG"
    return sc


def _hips_world(arm):
    return arm.matrix_world @ arm.pose.bones["mixamorig:Hips"].head


def render(arm, clip, out_dir):
    from PIL import Image

    sc = _setup(arm)
    cam = bpy.data.objects["preview_cam"]
    frames = range(sc.frame_start, sc.frame_end + 1)

    sc.frame_set(sc.frame_start)
    start = _hips_world(arm)
    sc.frame_set(sc.frame_end)
    end = _hips_world(arm)
    sprint = "Sprint" in clip

    tmp = os.path.join(out_dir, "_frames")
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for f in frames:
        sc.frame_set(f)
        h = _hips_world(arm)
        if sprint:
            # Follow cam: in front of the runner, off to the side, looking back.
            target = Vector((h.x * 0.6 + (start.x + end.x) * 0.2, h.y, 0.75))
            cam.location = target + Vector((2.0, -3.4, 0.45))
            cam.data.lens = 32
        else:
            mid = (start + end) / 2
            target = Vector((mid.x, mid.y, 0.6))
            cam.location = target + Vector((0.4, -3.9, 0.25))
            cam.data.lens = 50
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = os.path.join(tmp, f"{clip}_{f:03d}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)

    imgs = [Image.open(p).convert("RGB") for p in paths]
    small = [im.resize((RES_X * 3 // 4, RES_Y * 3 // 4), Image.LANCZOS) for im in imgs]
    small[0].save(os.path.join(out_dir, clip + ".gif"), save_all=True,
                  append_images=small[1:] + [small[-1]] * 8, duration=1000 // 30, loop=0)
    # Contact sheet of every other frame.
    picks = imgs[::2]
    cols = 3
    rows = (len(picks) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * RES_X, rows * RES_Y), (20, 20, 20))
    for i, im in enumerate(picks):
        sheet.paste(im, ((i % cols) * RES_X, (i // cols) * RES_Y))
    sheet.save(os.path.join(out_dir, clip + "_sheet.jpg"), quality=85)
    for p in paths:
        os.remove(p)
    os.rmdir(tmp)
    print("preview", clip, "->", out_dir)
