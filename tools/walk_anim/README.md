# ch_02 catwalk walk

Keyframe generator for `assets/animations/locomotion/ch_02_walk_catwalk.fbx`, matched against
`references/gippity6.gif`.

- 32-frame loop at 30 fps (frame 32 = frame 0), in place, Mixamo skeleton from `ch_02.fbx`
- Frame 0 = right-foot contact, frame 16 = left-foot contact
- Every bone is keyed on every frame; the Hips bone also carries location (bounce/sway)

What it reproduces from the reference:
- Feet cross over the midline on landing and roll off the toe
- The swing foot kicks up high behind the body (peaks ~9 frames after toe-off), then drops quickly into the next step
- The right foot flicks out to its own side, while the left foot kicks behind the stance leg. This asymmetry is in the reference (`SWING_X_BIAS`)
- The forward arm bends with the hand across the belly; the left fist rides higher, at chest level
- The back arm hangs nearly straight, out from the body, with the hand flared
- The pelvis sways over the stance foot, the stance hip pops up and the hips swivel; shoulders counter-rotate and the head stays steady

## Regenerate

Needs the `bpy` module (`pip install bpy`, Blender 5.2):

```
python tools/walk_anim/walk_gen.py assets/skeletal_meshes/characters/ch_02.fbx \
    assets/animations/locomotion/ch_02_walk_catwalk.fbx
```

## Compare with the reference

```
python tools/walk_anim/render_compare.py assets/skeletal_meshes/characters/ch_02.fbx \
    references/gippity6.gif /tmp/walk_cmp --azim -20
```

Each tile shows reference front | render front | render back | reference back. The cameras are yawed
by -20° because the subject in the reference is turned slightly relative to its cameras. The result is
in `docs/ch_02_walk_catwalk_vs_reference.gif`.
