# VIGIL — *the last light*

A 39-second cinematic cutscene starring `ch_02` (`assets/skeletal_meshes/characters/ch_02.fbx`),
built and animated entirely from code: no keyframes were placed by hand, no mocap, no
downloaded assets other than the character and its two textures.

**Watch:** [`vigil.mp4`](vigil.mp4) (1920×1080, 2.39:1 letterbox, 24 fps, stereo score).

> Night. A ruined gothic cathedral. She steps out of the mist in the west doorway and walks
> the length of the nave, past guttering candles and moonlit windows, to the place where the
> vault has fallen in. A single shaft of moonlight pours through the hole. She looks up into
> it, reaches, and closes her hand around the light — and it stays there, glowing in her fist,
> as the beam fades.

## Shot list

| # | Frames | Shot | Notes |
|---|--------|------|-------|
| 1 | 1–130 | **Doorway** — 30 mm, low, slow push | Silhouette against the misty exterior; she starts walking at f40 |
| 2 | 131–200 | **Boots** — 45 mm at ankle height, tracking | Heel strikes on wet flagstones, candle bokeh and reflections |
| 3 | 201–350 | **Walk, front** — 70 mm f/1.8, dolly back | Glances up at the moonlit windows (f220), down at candles (f304) |
| 4 | 351–480 | **Look up** — 15 mm, behind her | She slows into the beam and stops; camera tilts with her gaze to the broken vault and the moon |
| 5 | 481–620 | **Face** — 40 mm f/2.2 | Moonlight on her face; the hand rises into frame, focus racks to it |
| 6 | 621–690 | **Hand insert** — 42 mm, low | Fingers close on the light (f628–652); the beam collapses into her fist |
| 7 | 691–770 | **Glow** — 55 mm f/2 | The light held at her heart lights her face from below; she lifts her gaze |
| 8 | 771–840 | **Wide** — 32 mm, rising pull-back | Alone in the nave, the rose window ahead; fade to black |
| — | 841–936 | **Title** | VIGIL / *the last light* |

## How it is made

```
cinematics/vigil/
  build.py        entry point: builds the whole scene, optionally renders a frame range
  character.py    FBX import, shading, and a small FK / analytic two-bone IK solver
  performance.py  the procedural performance (gait + acting), baked to keys every frame
  environment.py  procedural cathedral: piers, arcades, clerestory, broken vault,
                  rose window, doors, pews, rubble, candles, banners, fog, dust
  materials.py    procedural (texture-free) shaders: ashlar, wet flagstones, wood...
  shots.py        lighting rig, 8 cameras + markers, render and compositor settings
  soundtrack.py   numpy-synthesised score and foley (no samples)
  finish.py       grade / grain / letterbox, title card, mux -> vigil.mp4
  stills/         one frame per shot
```

### Animation

The character ships with a Mixamo skeleton and no usable clips, so every motion is generated:

* **Pose maths** – each bone gets a rotation in *rest-aligned armature axes*
  (+X left, +Y up, +Z forward) applied on top of its parent's accumulated delta, so the
  choreography can say "pitch the spine 3° forward" without caring about bone rolls. The
  solver converts that to Blender's bone-local quaternions.
* **Footstep planner** – the pelvis follows a speed profile (ease in, cruise at 1.08 m/s,
  ease out). Steps fire every 14 frames; each foot plants where the pelvis will be at
  mid-stance (`s(contact + ½ step)`), which makes acceleration, deceleration and the final
  feet-together stop fall out naturally.
* **Legs** – analytic two-bone IK to ankle targets with heel-strike (toe up, pivot on heel),
  foot-flat slap, heel-off (pivot on the ball) and toe bend. Pelvis height is solved from
  leg reach every frame and smoothed, which produces the vertical bob for free.
* **Body layers** – pelvis yaw/roll/sway follow the feet, the spine counter-rotates, arms
  swing opposite the legs with a 3-frame lag, breathing rate and depth change with
  exertion, head/neck look-at with a human pitch limit, and small incommensurate-sine
  "life" noise.
* **Acting** – timed look targets (doorway → nave → windows → candles → the vault → her
  hand → her fist → ahead), a reach solved with arm IK and wrist orientation, a finger
  rig (spread / relaxed / fist with thumb opposition), and a weight shift into
  contrapposto when she stops.

### Set, light & sound

* Cathedral is generated with bmesh: pointed two-centred arches, slabs with window holes,
  a pointed barrel vault with a ragged collapse, a 16-spoke rose window with foils.
* Lighting: a cool moon through the side windows, a far, tight "grace beam" spotlight aimed
  through the hole onto her stop mark (cinematic cheat), door backlight into exterior fog,
  stained-glass glow, flickering candle clusters, and a point light bone-parented inside
  her right palm that takes over when the beam collapses.
* Rendered in Cycles (CPU) with a homogeneous fog volume, motion blur, OIDN, AgX, bloom and
  slight lens dispersion in the compositor; grain / vignette / grade in `finish.py`.
* The soundtrack is synthesised: convolution reverb from a generated cathedral impulse
  response, wind, a beating D drone, formant-filtered additive "choir" chords
  (Dm → B♭ → F → D major), footsteps placed on the exact heel-strike frames exported by the
  footstep planner, a reverse swell and chime when she catches the light, a heartbeat, and
  a boom + bell for the title.

## Reproduce

```bash
python -m venv venv && ./venv/bin/pip install bpy==5.2.2 pillow
./venv/bin/python cinematics/vigil/build.py --render --res 1280x536 --samples 16      # frames
python3 cinematics/vigil/soundtrack.py cinematics/vigil/renders/contacts.json cinematics/vigil/renders/vigil.wav
python3 cinematics/vigil/finish.py                                                     # -> vigil.mp4
```

`build.py --save-blend vigil.blend` writes the scene for inspection in Blender 5.2.
Inside Blender: `blender -b -P cinematics/vigil/build.py -- --render --frames 481-620`.
