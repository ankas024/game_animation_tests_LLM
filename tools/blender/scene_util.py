"""Scene loading + quick Workbench preview helpers (headless bpy)."""
import math
import os
import bpy
from mathutils import Vector

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHAR_FBX = os.path.join(REPO, "assets", "skeletal_meshes", "characters", "ch_02.fbx")


def load_character(fps=60):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=CHAR_FBX)
    # the source file carries a stray helper sphere and a 2-frame bind action
    ico = bpy.data.objects.get("Icosphere")
    if ico:
        bpy.data.objects.remove(ico)
    arm = bpy.data.objects["Armature"]
    if arm.animation_data:
        arm.animation_data.action = None
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.matrix_basis.identity()
    sc = bpy.context.scene
    sc.render.fps = fps
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    return arm, meshes


def add_camera(name, loc, target, lens=50.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return cam


def setup_workbench(res=(320, 400)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'OBJECT'
    sc.display.shading.show_cavity = False
    sc.display.shading.show_object_outline = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.world = sc.world or bpy.data.worlds.new("w")
    sc.render.image_settings.file_format = 'PNG'


def ground_grid():
    """A thin checker ground so foot contact/sliding is readable."""
    if "Ground" in bpy.data.objects:
        return bpy.data.objects["Ground"]
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=16, y_subdivisions=16, size=4.0)
    g = bpy.context.active_object
    g.name = "Ground"
    g.color = (0.55, 0.55, 0.6, 1)
    return g


def render_still(path, cam):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def montage(paths, out, cols, label=None):
    import subprocess
    args = ["montage"] + paths + ["-tile", f"{cols}x", "-geometry", "+2+2", "-background", "#222"]
    if label:
        args = ["montage", "-label", "%t"] + paths + ["-tile", f"{cols}x", "-geometry", "+2+2",
                                                      "-background", "#222", "-fill", "white", "-pointsize", "11"]
    subprocess.run(args + [out], check=True)
