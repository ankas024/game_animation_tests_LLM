# Game Animation Tests

## Layout

```
assets/
  skeletal_meshes/   characters/, creatures/, props/
  skeletons/         skeleton assets, rigs/
  physics_assets/
  materials/ textures/
  animations/
    locomotion/ combat/ idle/ interaction/ facial/
    additive/ poses/
    montages/ blend_spaces/ anim_blueprints/
    mocap/           raw/, retargeted/
tests/
  animation/ skeletal_meshes/
docs/
```

## LLM text VFX (Godot 4.5.1)

`project.godot` at the repo root opens a Godot 4.5.1 (Compatibility renderer) showcase of the character's
text-based VFX: disintegration into glyphs, dodge trails and afterimages, and the orb power.
See [docs/llm_text_vfx.md](docs/llm_text_vfx.md). Sources are in `vfx/`.
