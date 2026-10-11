# ch_02 — spear acrobatics

Side-by-side preview, both reference cameras (30 fps):
[`media/spear_acrobatics_compare.mp4`](media/spear_acrobatics_compare.mp4) ·
key poses: [`media/spear_acrobatics_keyposes.jpg`](media/spear_acrobatics_keyposes.jpg)

Each video frame is a 2×2 tile. The top row is reference view A next to ch_02 rendered from camera A. The
bottom row is reference view B next to ch_02 rendered from camera B. The renders use Workbench solid
shading with textures, i.e. Blender's viewport Solid mode with Color = Texture. ch_02 wears the
uploaded textures: `SK_c002_tripo_rgb_…jpg` on the body and `SK_c002_face_text_fix.png` on the head.

`references/spear_acrobatics/` is one take filmed twice. Frames 0–163 come from a low camera in front of
her, and frames 164–333 from a high camera behind her left shoulder. The second view starts 6 frames
earlier, so the animation is the full 170 frames (5.67 s). Animation frame k = reference frame k − 6
(view A) = reference frame 164 + k (view B).

## Breakdown (30 fps, 170 frames)

| Anim frames | View A frames | What happens |
|---|---|---|
| 0–6 | (B only) | Lead-in. Wide stance; the spear swings up from her right side into her left hand. |
| 6–14 | 0–8 | Weight onto the left leg, right knee up. Both hands take the spear overhead and whirl it, crescent first. |
| 14–24 | 8–18 | She drops into a deep crouch, turning to face right. The torso folds and the spear sweeps low. |
| 24–32 | 18–26 | Rises into a kneeling lunge; the spear does a flat spin at shoulder height. |
| 32–46 | 26–40 | Jump with a full turn to the left and a crescent kick with the left leg over the top. Tucks with the spear raised overhead, lands on the left foot. |
| 46–64 | 40–58 | Spins down into a very low side lunge, then prowls along the floor with the spear held over her back. |
| 64–74 | 58–68 | Squat; the spear is whirled overhead and round the body. |
| 74–88 | 68–82 | Hop, then a big jump, sitting in the air with the spear across her; she points it at the ground. |
| 88–102 | 82–96 | Stabs the spear blade-first into the ground and swings round the bending pole. Goes over the top into an inverted hold. |
| 102–122 | 96–116 | Pulls the spear out upside down, rolls back over in the air and lands on her left foot. |
| 122–140 | 116–134 | Crouch with the blade resting on the floor ahead of her, then rise. |
| 140–156 | 134–150 | Stands, swings the spear behind her back and round, and turns to face camera A. |
| 156–169 | 150–163 | End pose: spear held at the right hip, blade down to the floor in front of her left foot. |

## Files

| Path | Contents |
|---|---|
| `assets/animations/combat/A_ch02_SpearAcrobatics.fbx` | ch_02 skeleton plus the spear bones, both character meshes and the skinned spear. One baked 30 fps take, `A_ch02_SpearAcrobatics`, with every bone keyed on every frame and no curve simplification. Textures are referenced by relative path into `assets/textures/`. |
| `assets/animations/combat/A_ch02_SpearAcrobatics.json` | Frame mapping to both reference views, root motion, hip height range, frames where the spear touches or is planted in the floor. |
| `assets/textures/T_Spear.png` | 64×8 colour strip for the spear (silver shaft, blue fittings and blade). |
| `tools/spear_acrobatics/` | The generator: rig solver, keys, exporter, comparison renderer ([README](../tools/spear_acrobatics/README.md)). |
| `tests/animation/test_spear_acrobatics.py` | Re-imports the FBX and checks skeleton, length, pose vs. generator, ground contact, spear chain and the start/end poses. |

## Skeleton and spear

* The Mixamo hierarchy of `ch_02.fbx` is unchanged. Six bones are added for the spear, all under
  `mixamorig:Hips`, so there is still a single root: `weapon_spear` (centre → blade, the spear's
  main bone), `weapon_spear_f1`, `weapon_spear_f2` toward the blade, and `weapon_spear_b0…b2` toward the
  butt. Each bone is 1/6 of the 2.0 m spear. Bone +Y runs along the shaft; on the main bone +Z is the
  flat of the blade.
* The spear is a world-space object in this animation. She passes it between hands, plants it in the
  floor and vaults on it, so it is not parented to a hand. The hands are posed onto the shaft by IK.
* The chain bends: the pole visibly flexes while she swings on it (anim frames ~92–100), as in the
  reference. If you only need a rigid spear, attach a static mesh to `weapon_spear` and ignore the five
  other bones; the bend is only noticeable while the spear is planted.
* When planted (anim frames ~88–102) the blade is buried about 0.7 m in the floor plane.

## Root motion

There is no root bone; translation lives on `mixamorig:Hips`, as in the other ch_02 animations. The
take ends 0.27 m to screen-left of where it starts (`root_motion.net_displacement_m` in the JSON), squared
up to camera A instead of turned 35° to her right as at the start. Extract root motion from the Hips XY
in-engine if you need it.

## How it was made

Everything is generated from code (`tools/spear_acrobatics`); no mocap.

1. The reference was stepped through frame by frame. YOLO11 pose keypoints gave the hip track for
   view A, which sets the hip positions and jump heights. They are scaled by leg length because the
   reference character has a bigger head and a longer torso than ch_02.
2. Key poses were authored on 90 frames: hips, spine, head, legs (FK in the air, pinned feet on the
   floor), each hand (free, gripping the shaft, or carrying the spear) and the spear's direction,
   anchor and bend. Interpolation is monotone cubic per channel, plus a light low-pass.
3. Each pass was rendered next to the reference from both camera angles. The second angle fixed
   most of the spear's depth, which one view can't show (e.g. the end pose's spear points toward
   camera A, which is why it looks vertical from camera B). It also fixed which way she faces in the
   back swing and where she is relative to the pole.

## Known limitations

* ch_02's proportions differ from the reference character, so silhouettes never overlap exactly.
  The comparison cameras are scaled so leg lengths and jump heights line up.
* The fastest twirls (one-frame spear flips that are motion-blurred in the reference) are
  approximated. Some hand transitions show the hand reaching for the shaft for a frame or two.
* No hair, sash, skirt or cloth secondary motion: ch_02 has no bones for them.
* Camera B's direction (~140° round from A, ~25° down) and both reference cameras' pans were
  estimated from the footage, so absolute positions are approximate. Relative timing and poses are
  what was matched.
