# ch_02 — NieR-style sword combo

![preview](media/sword_combo_preview.gif)

60 fps preview (Workbench playblast): [`media/sword_combo_preview.mp4`](media/sword_combo_preview.mp4)
· key poses: [`media/sword_combo_keyposes.png`](media/sword_combo_keyposes.png)

The preview is a fast solid-shaded Workbench render. Trails and summon/dismiss
shards are flat translucent meshes, and the sword appears and vanishes through
the `weapon_r` scale. `render_preview.py --engine CYCLES` renders the same shot
with the full look: hilt→tip dissolve shader, glowing trails, bloom, impact
ring and motion blur. It runs at about 10 s/frame on 4 CPU cores.

A fast, flowing one-handed sword string in the spirit of 2B's light combo.
She summons the blade out of thin air with an iai-style draw and chains five
attacks as one continuous figure-8 flow. Each cut's follow-through winds up
the next. The string ends in a spinning cut, a launcher, a front flip and a
diving slam. She finishes with a fencer's point and a chiburi, the sword
shatters into light, and she settles into her idle pose. The combo travels
about 2.2 m forward. It ends on the new spot, facing the start direction.

## Breakdown (60 fps, 345 frames, 5.73 s)

| Frames | Beat | What happens |
|---|---|---|
| 0–10 | **Idle** | Relaxed contrapposto, empty hands. |
| 10–27 | **Coil** | Weight sinks onto the left leg and the body winds left. The right hand reaches across to an invisible scabbard at the left hip. |
| 27–44 | **Iai draw** | Explosive uncoil to the right. The right foot lunges out wide and a horizontal backhand sweeps across the front. Shards converge on the hand and the blade forms hilt → tip along the arc (flash at f38). |
| 44–70 | **1 · Forehand lunge cut** | The back foot closes up and the blade loops up behind the right shoulder. Then a high-right → low-left diagonal on a long right-foot lunge, with the hips down at 0.58 m (hit f60). |
| 70–92 | **2 · Backhand passing cut** | The blade loops up the left side and wraps behind the head as the left foot passes through ~1 m. Then a high-left → low-right diagonal that turns the body right (hit f85). |
| 92–128 | **3 · Spinning cut** | The turn keeps going: ~300° on the ball of the left foot, low and pitched forward. The sword is out front and the right leg stretches behind in an arabesque. The free arm starts wrapped across the chest and opens out to slow the turn. The head spots the target and whips round ahead of the body (hits f100, f116). |
| 128–150 | **4 · Launcher** | Lands facing forward and drops into a deep crouch with the sword low behind. A rising cut drives her off the ground (hit f147, takeoff f150). |
| 150–192 | **5 · Flip → diving slam** | Ballistic jump with ~0.7 m rise. A tucked front flip at the apex wheels the sword round her. It keeps wheeling forward out of the flip, over the top and straight down into the ground as she lands in a one-knee crouch (impact f192). |
| 192–214 | **Impact** | Recoil and a slow moving hold. |
| 214–238 | **Fencer's point** | Rises as the back foot steps up and turns out. The body goes side-on and the blade points at the target. |
| 238–272 | **Chiburi → twirl** | The blade wheels up over the shoulder and flicks down past the right leg (f246). She turns back square, then three quick turns of the sword in the hand. |
| 272–300 | **Dismiss** | The blade hangs low behind her right hip and breaks up tip → hilt (f280–300) while she glances down at it. |
| 300–344 | **Idle** | Two small steps into the idle pose on the new spot. The last frame is frame 0's pose shifted by the root motion, so it blends straight into `A_ch02_Idle_Loop`. |

## Files

| Path | Contents |
|---|---|
| `assets/animations/combat/A_ch02_SwordCombo.fbx` | Skeleton plus `weapon_r`, both character meshes, the skinned placeholder sword, and the baked 60 fps action. Every frame is keyed, with no curve simplification. |
| `assets/animations/combat/A_ch02_SwordCombo.events.json` | Notify frames and times, the summon/dismiss/airborne windows, root-motion data (net displacement plus per-frame `RootMotionX/Y` curves) and a per-frame `SwordMaterialize` curve (0 = gone, 1 = solid). |
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
  translation: it slides 4–5 cm out of the palm during twirls so the
  blade clears the forearm.
* **Materialise / vanish:** `weapon_r` scale goes to ~0 whenever the sword
  doesn't exist. That way any viewer shows the sword appearing and
  disappearing with no extra setup. In-engine, also drive a dissolve material
  from `curves.SwordMaterialize` (or from the `summon_*` / `dismiss_*`
  notifies). The preview's dissolve reveals hilt → tip on summon and
  tip → hilt on dismiss, with a hot edge at the front.

## Root motion

There is no root bone in this rig, so all translation lives on
`mixamorig:Hips`. The combo travels **2.2 m forward** (`net_displacement_m` in
`events.json`) and ends facing the start direction (`net_yaw_deg` = 0).
`curves.RootMotionX/Y` hold the floor-projected hips path, low-passed so the
step bob and weight shifts stay in the animation. They are in character
space: metres, +x right, +y forward, frame 0 = origin.

* **In place:** play it as is and the character walks off its capsule. Move
  the actor by `net_displacement_m` when the montage ends.
* **Root motion:** add a root bone at the origin and key it from
  `RootMotionX/Y` (subtract the same values from the Hips XY), or let the
  engine extract root motion from the Hips XY.

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
`tools/blender/combo.py` as key poses (hips, spine, planted feet) plus
Catmull-Rom sword paths (blade direction, grip direction, reach) sampled
every frame. The cutting edge comes from the path, so it always leads.
`timeline.py` interpolates the keys and then post-processes every channel:

* damped springs on the spine, head, free arm and hip tilt for follow-through
  and settle
* a Gaussian low-pass on everything, which removes velocity kinks; the combo
  has no hard ease seams

The solver in `rigkit.py` turns channels into bone rotations: FK spine, soft
two-bone IK with an automatic elbow swivel, ball-pivot feet, finger curls.
For the sword arm it pre-computes where the grip has to be for the wrist to
stay in range, so the blade follows its authored path. That correction is
baked into the hand curves and smoothed as well.

```bash
pip install bpy==5.1.2                                    # Blender as a Python module (py3.13)
python -I tools/blender/diag.py                           # numeric checks: foot slide, floor, wrists, blade-vs-body, reach
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
* The arms are short for a ~0.9 m sword (0.26 m shoulder → wrist). The
  sword hand gives up ~4 cm of reach on average so the wrist stays within
  ~68° of bend.
* The rig has no cloth or hair bones, so there's no secondary motion on the
  sleeves or skirt.
* The sword is a placeholder. Its proportions are ~0.9 m overall for the
  1.25 m tall character.
