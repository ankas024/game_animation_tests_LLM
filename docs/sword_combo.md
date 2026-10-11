# ch_02 — NieR-style sword combo

![preview](media/sword_combo_preview.gif)

60 fps preview (Workbench playblast): [`media/sword_combo_preview.mp4`](media/sword_combo_preview.mp4)
· key poses: [`media/sword_combo_keyposes.png`](media/sword_combo_keyposes.png)

The preview is a fast solid-shaded Workbench render. Trails and summon/dismiss
shards are flat translucent meshes, and the sword appears and vanishes through
the `weapon_r` scale. `render_preview.py --engine CYCLES` renders the same shot
with the full look: hilt→tip dissolve shader, glowing trails, bloom, impact
ring and motion blur. It runs at about 10 s/frame on 4 CPU cores.

A fast, flowing one-handed sword string in the spirit of 2B's light combo:
the blade is summoned out of thin air with an iai-style draw, five attacks
chain into each other, and the sword shatters into light before she settles
back into her idle pose. It starts and ends on the exact idle pose, on the
same spot and facing the same way.

## Breakdown (60 fps, 381 frames, 6.33 s)

| Frames | Beat | What happens |
|---|---|---|
| 0–30 | **Idle** | Relaxed contrapposto, empty hands. |
| 30–58 | **Summon** | Reaches across to the left hip as if gripping a hidden scabbard, then whips an iai draw across the front. Shards of light converge on the hand and the blade forms hilt → tip along the arc (flash at f55). |
| 58–84 | **Flourish → guard** | One spin of the sword in the hand, then a low trailing guard, blade behind and down, with the left hand forward. |
| 84–106 | **1 · Rising slash** | Right foot steps in. Low-right → high-left diagonal (hit f96). |
| 105–126 | **2 · Descending slash** | Wrist re-chambers overhead. Left foot steps in. High-left → low-right backhand (hit f116). |
| 126–166 | **3 · Spin slash** | Full 360° turn pivoting on the left ball of the foot. The blade sweeps flat at waist height, the head spots ahead of the body, and the free arm tucks in for speed (hits f136, f155). |
| 164–186 | **4 · Launcher** | Deep crouch, rising backhand cut, takeoff at f178 (hit f179). |
| 184–205 | **5 · Front-flip plunge** | Tucked front flip at the apex with the blade wheeling around her, then a straight-down slam into a kneeling "superhero" landing (impact f205). |
| 205–222 | **Impact hold** | Recoil and hold. |
| 222–262 | **Rise → twirl → chiburi** | Stands up, spins the sword twice in her fingers beside the leg, then snaps a blood-flick down and out to the side (f258). |
| 262–300 | **Back-hop** | A light backwards jump that returns her to her starting spot, sword trailing low. |
| 300–352 | **Dismiss** | She glances at the blade as it breaks into shards from tip to hilt (f304–326), the hand opens, and she steps back into idle. |
| 352–380 | **Idle** | Same pose as frame 0, so it blends straight into `A_ch02_Idle_Loop`. |

## Files

| Path | Contents |
|---|---|
| `assets/animations/combat/A_ch02_SwordCombo.fbx` | Skeleton plus `weapon_r`, both character meshes, the skinned placeholder sword, and the baked 60 fps action. Every frame is keyed, with no curve simplification. |
| `assets/animations/combat/A_ch02_SwordCombo.events.json` | Notify frames and times, the summon/dismiss/airborne windows, and a per-frame `SwordMaterialize` curve (0 = gone, 1 = solid). |
| `assets/animations/combat/source/A_ch02_SwordCombo.blend` | Editable Blender 5.1 scene with the baked action. |
| `assets/animations/idle/A_ch02_Idle_Loop.fbx` | 240-frame seamless idle loop: two breaths and a slow weight shift. Frame 0 is the combo's first and last pose. |
| `assets/skeletal_meshes/props/SM_Sword_Placeholder.fbx` | Standalone sword static mesh. The pivot is at the centre of the fist on the grip. |
| `tools/blender/` | The generator: rig solver, choreography, exporter, preview renderer. |
| `tests/animation/test_sword_combo.py` | Re-imports the exported FBX files and checks them. |

## Skeleton & sword

* The original Mixamo hierarchy of `ch_02.fbx` is untouched, with identical
  rest pose. One bone is added: **`weapon_r`**, a child of
  `mixamorig:RightHand`, with its head at the centre of the fist on the grip.
  * bone **+Y** points along the blade to the tip
  * bone **+X** points to the cutting edge
  * bone **+Z** is the flat of the blade
* The sword mesh in the combo FBX is skinned 100% to `weapon_r`. The prop FBX
  uses the same local frame, so attaching `SM_Sword_Placeholder` to a socket
  on `weapon_r` with an identity transform gives the same result.
* `weapon_r` is animated in rotation (the in-hand twirls) and slightly in
  translation: it slides about 3.5 cm out of the palm during spins so the
  blade clears the forearm.
* **Materialise / vanish:** `weapon_r` scale goes to ~0 whenever the sword
  doesn't exist. That way any viewer shows the sword appearing and
  disappearing with no extra setup. In-engine, also drive a dissolve material
  from `curves.SwordMaterialize` (or from the `summon_*` / `dismiss_*`
  notifies). The preview's dissolve reveals hilt → tip on summon and
  tip → hilt on dismiss, with a hot edge at the front.

## Root motion

There is no root bone in this rig, so all translation lives on
`mixamorig:Hips`. The combo travels about 1 m forward, and the back-hop
brings her back. The last frame is the first frame's pose: same spot, same
facing. So it plays correctly in place. To use root motion, add a root bone
and extract the Hips XY between `hit_1` and `hop_land`.

## Engine notes

* **Unreal:** import `A_ch02_SwordCombo.fbx` as a Skeletal Mesh first, or
  merge it into the existing ch_02 Skeleton so `weapon_r` gets added. Then
  re-import the animation onto that skeleton with *Import Mesh* off. Create
  Anim Notifies from `events.json`; the sword attach socket is `weapon_r`.
* **Unity:** use the **Generic** rig to keep `weapon_r`. With **Humanoid**,
  the body retargets fine but `weapon_r` needs to be added as an extra
  transform in the avatar mask.
* FBX settings: −Z forward, Y up, cm units (matches the source file).

## Regenerating / tweaking

Everything is generated from code. The choreography lives in
`tools/blender/combo.py` as key poses: sword blade/edge vectors, hand
directions, planted feet. The solver in `rigkit.py` turns them into bone
rotations (FK spine, soft two-bone IK with an automatic elbow swivel that
keeps the wrist neutral, a wrist limit cone, ball-pivot feet, and finger
curls).

```bash
pip install bpy==5.1.2                                    # Blender as a Python module (py3.13)
python -I tools/blender/diag.py                           # numeric checks: foot slide, floor, wrists, blade-vs-body
python -I tools/blender/review.py OUT q34,side 84-130:3 tag   # Workbench contact sheets
python -I tools/blender/export_assets.py                  # FBX + events.json + .blend
python -I tools/blender/render_preview.py --out OUT --engine WORKBENCH --fast --res 960x540   # playblast, ~0.1 s/frame
tools/blender/make_media.sh OUT                           # mp4 + gif + key-pose sheet into docs/media
python -I tests/animation/test_sword_combo.py
```

## Known limitations

* `ch_02.fbx` references a texture (`tripo_rgb_….png`) that isn't in the repo.
  The exports drop that dangling reference, and the preview uses a neutral
  clay shader.
* The rig has no twist bones. About 60% of the forearm roll is pushed into
  the forearm bone, and large wrist rolls (~70°) still show some candy-wrap
  on the cuff.
* The rig has no cloth or hair bones, so there's no secondary motion on the
  sleeves or skirt.
* The sword is a placeholder. Its proportions are ~0.9 m overall for the
  1.25 m tall character.
