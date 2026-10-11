# ch_02 spear acrobatics

Keyframe generator for `assets/animations/combat/A_ch02_SpearAcrobatics.fbx`, matched against
`references/spear_acrobatics/`. Write-up and preview: [`docs/spear_acrobatics.md`](../../docs/spear_acrobatics.md).

The reference folder shows the same take twice, from two cameras:

| View | Reference frames | Camera |
|---|---|---|
| A | 0–163 | low, in front of her start/end facing |
| B | 164–333 | high (~25° down), behind her left shoulder (~140° round from A) |

B is A + 170 frames and starts 6 frames earlier, so the animation is 170 frames at 30 fps.
Animation frame k = view A frame k − 6 = view B frame 164 + k. Frame 334 is the first frame of the next
reel item and is not used.

## Files

| File | What it does |
|---|---|
| `rig.py` | Pose solver for the Mixamo rig plus the spear: hips with full 3D rotation (flips), FK spine/head, legs blended FK ↔ IK (ball of the foot pinned), arms that either pose freely, grip the shaft (fist closed round it, slides along it if the authored grip is out of reach), or carry the spear (the hand leads, the spear follows). The spear is a 6-bone chain with constant-curvature bending. |
| `keys.py` | The choreography: key poses read off the reference, frame numbers are view-A frames (−6 … 163). Hip positions come from a YOLO pose keypoint track of view A, scaled by leg length. |
| `keylib.py` | Small helpers for writing keys. |
| `timeline.py` | Per-channel monotone cubic (PCHIP) interpolation, spear-angle unwrapping, light Gaussian smoothing. |
| `clips.py` | Frame mapping and the two comparison cameras. |
| `scene.py` | Loads `ch_02.fbx`, wires the uploaded textures into its materials, builds the spear bones, mesh and texture, sets up Workbench solid + texture shading. |
| `build.py` | Bakes every bone on every frame and exports the FBX and a JSON sidecar. |
| `render_compare.py` | Renders the animation from both reference cameras next to the reference frames. |

## Regenerate

Needs the `bpy` module (`pip install bpy`, Blender 5.2):

```
python -I tools/spear_acrobatics/build.py                  # FBX + JSON into assets/animations/combat
python -I tests/animation/test_spear_acrobatics.py         # re-import and check
```

## Compare with the reference

```
python -I tools/spear_acrobatics/render_compare.py /tmp/spear_cmp --res 640x360 --mp4
```

Each frame is a 2×2 tile: view A reference | render from camera A, view B reference | render from camera
B. Rendering is Workbench (Solid shading, Color = Texture, outdoor studio light), i.e. what Blender's
viewport shows in Solid mode with textures. `--frames -6-163:2` renders a subset (view-A frame numbers),
`--views A` one camera only.
