"""Viewport-solid (Workbench) playblast of a saved VIGIL scene through the shot cameras.

    python cinematics/vigil/build.py --save-blend vigil.blend
    python cinematics/vigil/playblast_solid.py -- vigil.blend out_dir 1-840

Needs an OpenGL/EGL context (e.g. Mesa libegl1 on a headless Linux box).
"""
import bpy, sys, os, time
argv = sys.argv[sys.argv.index("--") + 1:]
blend, out, frames = argv[0], argv[1], argv[2]
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "MATERIAL"
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.show_shadows = False
sh.show_object_outline = True
sc.display.render_aa = "8"
sc.render.use_compositing = False
sc.render.use_motion_blur = False
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
for o in bpy.data.objects:
    if o.name.startswith(("fog_", "moon", "fist_core", "motes")):
        o.hide_render = True
    if o.type == "CAMERA":
        o.data.dof.use_dof = False
os.makedirs(out, exist_ok=True)
if "-" in frames:
    a, b = map(int, frames.split("-")); fl = range(a, b + 1)
else:
    fl = [int(x) for x in frames.split(",")]
for f in fl:
    t = time.time()
    sc.frame_set(f)
    live = [m for m in sc.timeline_markers if m.frame <= f and m.camera]
    sc.camera = max(live, key=lambda m: m.frame).camera
    sc.render.filepath = f"{out}/solid_{f:04d}.png"
    bpy.ops.render.render(write_still=True)
    print(f"[solid] {f} {time.time()-t:.2f}s", flush=True)
