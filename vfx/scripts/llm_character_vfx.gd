## Drives every VFX layer on the LLM character:
##   * swaps the imported materials for llm_character.gdshader and bakes the rest
##     pose into CUSTOM0 so glyphs / dissolve cells stick to the skin
##   * plays the dodge / idle clips (hips root motion is folded back into the node)
##   * dash VFX: text afterimages, limb token ribbons, body wake sheet, glitch
##     slicing, glyph shedding
##   * disintegrate / reassemble with particles spawned at the exact voxels the
##     shader is erasing (CPU mirror of the dissolve field + CPU skinning)
##   * orb form transitions (body collapses into / unfolds out of an LlmOrb)
class_name LlmCharacterVfx
extends Node3D

signal dodge_started(kind: String)
signal dodge_finished(kind: String)

const MODEL := preload("res://assets/skeletal_meshes/characters/ch_02.fbx")
const BODY_TEX := preload("res://assets/textures/SK_c002_tripo_rgb_69d181a3-f4af-4255-8e04-1ec596474e7e.jpg")
const HEAD_TEX := preload("res://assets/textures/SK_c002_face_text_fix.png")
const ATLAS := preload("res://vfx/textures/glyph_atlas.png")
const CHAR_SHADER := preload("res://vfx/shaders/llm_character.gdshader")
const GHOST_SHADER := preload("res://vfx/shaders/llm_afterimage.gdshader")

const CLIPS := {
	"idle": "res://assets/animations/idle/A_ch02_Idle_Loop.fbx",
	"dodge_stand_r": "res://assets/animations/combat/dodge/A_Dodge_Stand_R.fbx",
	"dodge_stand_l": "res://assets/animations/combat/dodge/A_Dodge_Stand_L.fbx",
	"dodge_sprint_r": "res://assets/animations/combat/dodge/A_Dodge_Sprint_R.fbx",
	"dodge_sprint_l": "res://assets/animations/combat/dodge/A_Dodge_Sprint_L.fbx",
}
# i-frame windows from docs/dodge_animations.md (30 fps frames) -> VFX window
const DODGE_WINDOW := {
	"stand": Vector2(2.0 / 30.0, 12.0 / 30.0),
	"sprint": Vector2(3.0 / 30.0, 16.0 / 30.0),
}
const TRAIL_BONES := {
	"mixamorig_LeftHand": 0.62, "mixamorig_RightHand": 0.62,
	"mixamorig_LeftFoot": 0.70, "mixamorig_RightFoot": 0.70,
	"mixamorig_Head": 0.5,
}
const CHEST_REST := Vector3(0.0, 0.98, 0.0)

@export var swarm: GlyphSwarm
@export var fx_root: Node3D

var skeleton: Skeleton3D
var anim: AnimationPlayer
var materials: Array[ShaderMaterial] = []

var dissolve_progress := 0.0:
	set(v):
		dissolve_progress = v
		_set_all("dissolve_progress", v)
var glitch := 0.0:
	set(v):
		glitch = v
		_set_all("glitch", v)
var overdrive := 0.0:
	set(v):
		overdrive = v
		_set_all("overdrive", v)
var data_skin := 0.25:
	set(v):
		data_skin = v
		_set_all("data_skin", v)

var is_dodging := false
var current_clip := ""

# dissolve shape (mirrors shader uniforms)
var _d_origin := Vector3.ZERO
var _d_axis := Vector3.UP
var _d_extent := 1.3
var _d_radial := 0.0
var _d_noise := 0.35
var _d_band := 0.16
var _d_voxel := 0.035

# CPU skinning data, per mesh: {mi, verts, bones, weights, nw, binds, bind_poses}
var _skin_data: Array[Dictionary] = []
var _samples: Array[Dictionary] = []  # pre-picked surface points with dissolve field values
var _sample_cursor := 0

var _hips_idx := -1
var _prev_hips := Vector3.ZERO
var _hips_vel := Vector3.ZERO
var _trails: Array[TokenRibbonTrail] = []
var _wake: TokenRibbonTrail
var _ghosts: Array[Dictionary] = []
var _dodge_t := 0.0
var _dodge_kind := ""
var _dodge_len := 0.0
var _ghost_timer := 0.0
var _ghost_count := 0

# active dissolve operation
var _op := {}


func _ready() -> void:
	var model := MODEL.instantiate()
	model.name = "Model"
	add_child(model)
	model.get_node("Icosphere").visible = false
	skeleton = model.get_node("Armature/Skeleton3D")
	anim = model.get_node("AnimationPlayer")
	_hips_idx = skeleton.find_bone("mixamorig_Hips")
	_setup_meshes()
	_setup_animations()
	_setup_trails()
	set_dissolve_shape_linear(Vector3(0, -0.02, 0), Vector3.UP, 1.3, 0.35)
	play_idle()
	_prev_hips = hips_world()


# ---------------------------------------------------------------- setup ----
func _setup_meshes() -> void:
	for mi_name in ["c002_body", "c002_head"]:
		var mi: MeshInstance3D = skeleton.get_node(mi_name)
		var src: ArrayMesh = mi.mesh
		var arrays := src.surface_get_arrays(0)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var n := verts.size()
		var custom := PackedFloat32Array()
		custom.resize(n * 4)
		for i in n:
			var v := verts[i]
			custom[i * 4] = v.x
			custom[i * 4 + 1] = v.y
			custom[i * 4 + 2] = v.z
			custom[i * 4 + 3] = 0.0
		arrays[Mesh.ARRAY_CUSTOM0] = custom
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var nw := bones.size() / n
		var flags := Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT
		if nw == 8:
			flags |= Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
		var m := ArrayMesh.new()
		m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, flags)
		mi.mesh = m
		var mat := ShaderMaterial.new()
		mat.shader = CHAR_SHADER
		mat.set_shader_parameter("albedo_tex", BODY_TEX if mi_name == "c002_body" else HEAD_TEX)
		mat.set_shader_parameter("glyph_atlas", ATLAS)
		mi.material_override = mat
		materials.append(mat)

		var binds := PackedInt32Array()
		var bind_poses: Array[Transform3D] = []
		var skin: Skin = mi.skin
		for b in skin.get_bind_count():
			var bi := skin.get_bind_bone(b)
			if bi < 0:
				bi = skeleton.find_bone(skin.get_bind_name(b))
			binds.append(bi)
			bind_poses.append(skin.get_bind_pose(b))
		_skin_data.append({"mi": mi, "verts": verts, "bones": bones, "weights": weights,
			"nw": nw, "binds": binds, "bind_poses": bind_poses})


func _setup_animations() -> void:
	var lib := AnimationLibrary.new()
	for key in CLIPS:
		var scene: Node = load(CLIPS[key]).instantiate()
		var ap: AnimationPlayer = scene.find_child("AnimationPlayer", true, false)
		var a: Animation = ap.get_animation(ap.get_animation_list()[0]).duplicate(true)
		a.loop_mode = Animation.LOOP_LINEAR if key == "idle" else Animation.LOOP_NONE
		lib.add_animation(key, a)
		scene.free()
	anim.add_animation_library("vfx", lib)
	anim.animation_finished.connect(_on_anim_finished)


func _setup_trails() -> void:
	var parent := fx_root if fx_root else self
	for bone in TRAIL_BONES:
		var ba := BoneAttachment3D.new()
		ba.bone_name = bone
		skeleton.add_child(ba)
		var tr := TokenRibbonTrail.new()
		tr.target = ba
		tr.width = 0.075 if bone.ends_with("Hand") or bone.ends_with("Head") else 0.09
		tr.lifetime = 0.42
		parent.add_child.call_deferred(tr)
		tr.set_param("hue", TRAIL_BONES[bone])
		tr.set_param("rows", 1.0)
		tr.set_param("core_width", 0.18)
		tr.set_param("scroll_speed", 3.0)
		tr.set_param("intensity", 2.4)
		_trails.append(tr)
	var hips_ba := BoneAttachment3D.new()
	hips_ba.bone_name = "mixamorig_Hips"
	skeleton.add_child(hips_ba)
	_wake = TokenRibbonTrail.new()
	_wake.target = hips_ba
	_wake.orient = TokenRibbonTrail.Orient.SHEET
	_wake.width = 1.25
	_wake.sheet_offset = Vector3(0, -0.2, 0)
	_wake.lifetime = 0.5
	_wake.taper = true
	parent.add_child.call_deferred(_wake)
	_wake.set_param("rows", 14.0)
	_wake.set_param("hue", 0.55)
	_wake.set_param("hue_spread", 0.4)
	_wake.set_param("core_width", 0.0)
	_wake.set_param("intensity", 0.75)
	_wake.set_param("scroll_speed", 5.0)
	_wake.set_param("glyph_fill", 0.45)
	_wake.set_param("edge_softness", 1.0)


# -------------------------------------------------------------- helpers ----
func _set_all(param: String, v: Variant) -> void:
	for m in materials:
		m.set_shader_parameter(param, v)


func hips_world() -> Vector3:
	return skeleton.global_transform * skeleton.get_bone_global_pose(_hips_idx).origin


func chest_world() -> Vector3:
	return skeleton.global_transform * (skeleton.get_bone_global_pose(skeleton.find_bone("mixamorig_Spine2")).origin + Vector3(0, -0.01, 0.03))


func set_dissolve_shape_linear(origin: Vector3, axis: Vector3, extent: float, noise := 0.35) -> void:
	_apply_shape(origin, axis.normalized(), extent, 0.0, noise)


func set_dissolve_shape_radial(origin: Vector3, extent: float, noise := 0.3) -> void:
	_apply_shape(origin, Vector3.UP, extent, 1.0, noise)


func _apply_shape(origin: Vector3, axis: Vector3, extent: float, radial: float, noise: float) -> void:
	_d_origin = origin; _d_axis = axis; _d_extent = extent; _d_radial = radial; _d_noise = noise
	_set_all("dissolve_origin", origin)
	_set_all("dissolve_axis", axis)
	_set_all("dissolve_extent", extent)
	_set_all("dissolve_radial", radial)
	_set_all("dissolve_noise", noise)
	_set_all("dissolve_band", _d_band)
	_set_all("voxel_size", _d_voxel)


func field_of(rest: Vector3) -> float:
	return GlyphHash.dissolve_field(rest, _d_origin, _d_axis, _d_extent, _d_radial, _d_noise, _d_voxel)


## Skinned world position of a vertex (CPU skinning, same maths as the GPU).
func skinned_world(mesh_i: int, v: int) -> Vector3:
	var sd: Dictionary = _skin_data[mesh_i]
	var nw: int = sd.nw
	var verts: PackedVector3Array = sd.verts
	var bones: PackedInt32Array = sd.bones
	var weights: PackedFloat32Array = sd.weights
	var binds: PackedInt32Array = sd.binds
	var bind_poses: Array[Transform3D] = sd.bind_poses
	var rest := verts[v]
	var acc := Vector3.ZERO
	var wsum := 0.0
	for k in nw:
		var w := weights[v * nw + k]
		if w <= 0.0:
			continue
		var bi := bones[v * nw + k]
		var xf := skeleton.get_bone_global_pose(binds[bi]) * bind_poses[bi]
		acc += (xf * rest) * w
		wsum += w
	if wsum > 0.0:
		acc /= wsum
	return skeleton.global_transform * acc


## Pick `count` random surface vertices, sorted by their dissolve field value.
func _build_samples(count: int) -> void:
	_samples.clear()
	var total := 0
	for sd in _skin_data:
		total += (sd.verts as PackedVector3Array).size()
	for i in count:
		var r := randi() % total
		var mesh_i := 0
		while r >= (_skin_data[mesh_i].verts as PackedVector3Array).size():
			r -= (_skin_data[mesh_i].verts as PackedVector3Array).size()
			mesh_i += 1
		var rest: Vector3 = _skin_data[mesh_i].verts[r]
		_samples.append({"m": mesh_i, "v": r, "f": field_of(rest)})
	_samples.sort_custom(func(a, b): return a.f < b.f)
	_sample_cursor = 0


func _threshold(p: float) -> float:
	return p * (1.0 + _d_band) - _d_band


# ------------------------------------------------------------ animation ----
func play_idle(blend := 0.0) -> void:
	anim.play("vfx/idle", blend)
	current_clip = "idle"


## kind: "stand_r", "stand_l", "sprint_r", "sprint_l"
func dodge(kind: String) -> void:
	if is_dodging:
		return
	var clip := "vfx/dodge_" + kind
	anim.play(clip, 0.08)
	current_clip = clip
	is_dodging = true
	_dodge_kind = kind
	_dodge_t = 0.0
	_dodge_len = anim.get_animation(clip).length
	_ghost_timer = 0.0
	_ghost_count = 0
	dodge_started.emit(kind)


func _on_anim_finished(name: StringName) -> void:
	if not String(name).begins_with("vfx/dodge_"):
		return
	# fold the hips root motion into this node, then return to idle
	var before := hips_world()
	play_idle(0.0)
	anim.advance(0.0)
	var after := hips_world()
	var delta := before - after
	delta.y = 0.0
	global_position += delta
	_prev_hips = hips_world()
	is_dodging = false
	for t in _trails:
		t.emitting = false
	_wake.emitting = false
	dodge_finished.emit(_dodge_kind)


# ------------------------------------------------------------ afterimage ---
func spawn_afterimage(hue: float, life_time := 0.55) -> void:
	var dup: Skeleton3D = skeleton.duplicate(0)
	for c in dup.get_children():
		if not (c is MeshInstance3D):
			c.free()
	for i in skeleton.get_bone_count():
		dup.set_bone_pose_position(i, skeleton.get_bone_pose_position(i))
		dup.set_bone_pose_rotation(i, skeleton.get_bone_pose_rotation(i))
		dup.set_bone_pose_scale(i, skeleton.get_bone_pose_scale(i))
	var holder := Node3D.new()
	(fx_root if fx_root else get_parent()).add_child(holder)
	holder.global_transform = skeleton.global_transform
	holder.add_child(dup)
	dup.transform = Transform3D.IDENTITY
	var mat := ShaderMaterial.new()
	mat.shader = GHOST_SHADER
	mat.set_shader_parameter("glyph_atlas", ATLAS)
	mat.set_shader_parameter("hue", hue)
	var v := _hips_vel
	v.y = 0.0
	var smear := -(skeleton.global_basis.inverse() * v).normalized() if v.length() > 0.1 else Vector3(0, 0, -1)
	mat.set_shader_parameter("smear_dir", smear)
	for c in dup.get_children():
		if c is MeshInstance3D:
			c.material_override = mat
			c.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_ghosts.append({"node": holder, "mat": mat, "t": 0.0, "len": life_time})


# ------------------------------------------------------------ dissolve ops --
## Linear sweep dissolve into drifting text. dir: model-space sweep direction.
func disintegrate(duration := 1.8, dir := Vector3.UP, wind := Vector3(0.6, 0.0, -0.2)) -> void:
	var origin := Vector3(0, -0.02, 0) if dir.y >= 0.0 else Vector3(0, 1.27, 0)
	set_dissolve_shape_linear(origin, dir, 1.32, 0.35)
	_build_samples(5000)
	_op = {"kind": "out", "t": 0.0, "len": duration, "mode": GlyphSwarm.Mode.DRIFT, "wind": wind}


## Reverse of disintegrate: glyphs fly in and are written back into the body.
func reassemble(duration := 1.8, dir := Vector3.DOWN, source := Vector3.INF) -> void:
	visible = true
	var origin := Vector3(0, -0.02, 0) if dir.y >= 0.0 else Vector3(0, 1.27, 0)
	set_dissolve_shape_linear(origin, dir, 1.32, 0.35)
	_start_reform(duration, source)


## Body collapses into the orb at the chest.
func collapse_to_orb(orb: Node3D, duration := 1.4) -> void:
	set_dissolve_shape_radial(CHEST_REST, 0.78, 0.28)
	_build_samples(4500)
	swarm.attractor = orb
	_op = {"kind": "out", "t": 0.0, "len": duration, "mode": GlyphSwarm.Mode.ATTRACT}


## Body unfolds out of the orb.
func unfold_from_orb(orb: Node3D, duration := 1.4) -> void:
	visible = true
	set_dissolve_shape_radial(CHEST_REST, 0.78, 0.28)
	_start_reform(duration, orb.global_position)


func _start_reform(duration: float, source: Vector3) -> void:
	_build_samples(2600)
	dissolve_progress = 1.0
	# schedule each glyph to land exactly when its voxel reappears
	var travel := 0.45
	var sched: Array[Dictionary] = []
	for s in _samples:
		# p(t) = 1 - t/len ; reappears when threshold(p) < f
		var p_at: float = (s.f + _d_band) / (1.0 + _d_band)
		var t_arrive := duration * (1.0 - clampf(p_at, 0.0, 1.0))
		sched.append({"s": s, "t": t_arrive - travel})
	sched.sort_custom(func(a, b): return a.t < b.t)
	_op = {"kind": "in", "t": -travel, "len": duration, "sched": sched, "cursor": 0,
		"travel": travel, "source": source}


func is_busy() -> bool:
	return not _op.is_empty()


func _process_op(delta: float) -> void:
	if _op.is_empty():
		return
	_op.t += delta
	var t: float = _op.t
	var dur: float = _op.len
	if _op.kind == "out":
		var p := clampf(t / dur, 0.0, 1.0)
		dissolve_progress = p
		overdrive = sin(p * PI) * 0.8
		var thr := _threshold(p)
		var mode: int = _op.mode
		var budget := 90
		while _sample_cursor < _samples.size() and _samples[_sample_cursor].f < thr and budget > 0:
			var s: Dictionary = _samples[_sample_cursor]
			_sample_cursor += 1
			budget -= 1
			var wp := skinned_world(s.m, s.v)
			var col := _token_color(randf())
			if mode == GlyphSwarm.Mode.DRIFT:
				var wind: Vector3 = _op.wind
				var vel := wind + Vector3(randf_range(-0.3, 0.3), randf_range(0.2, 0.9), randf_range(-0.3, 0.3))
				swarm.emit(wp, vel, col, randf_range(1.2, 2.2), randf_range(0.022, 0.04), mode, Vector3.ZERO, 14.0)
			else:
				var away := (wp - swarm.attractor.global_position).normalized()
				swarm.emit(wp, away * randf_range(0.6, 1.4) + Vector3.UP * 0.4, col, 3.0, randf_range(0.025, 0.04), mode, Vector3.ZERO, 20.0)
		if t >= dur:
			# skip the remaining samples that weren't emitted this frame
			_sample_cursor = _samples.size()
			dissolve_progress = 1.0
			overdrive = 0.0
			visible = false
			_op = {}
	else:
		var p := clampf(1.0 - t / dur, 0.0, 1.0)
		dissolve_progress = p
		overdrive = sin(p * PI) * 0.8
		var sched: Array = _op.sched
		var travel: float = _op.travel
		var source: Vector3 = _op.source
		while _op.cursor < sched.size() and sched[_op.cursor].t <= t:
			var s: Dictionary = sched[_op.cursor].s
			_op.cursor += 1
			var target := skinned_world(s.m, s.v)
			var from: Vector3
			if source == Vector3.INF:
				from = target + Vector3(randf_range(-1, 1), randf_range(-0.3, 1.2), randf_range(-1, 1)).normalized() * randf_range(0.6, 1.4)
			else:
				from = source + Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1)) * 0.12
			swarm.emit(from, Vector3.ZERO, _token_color(randf()), travel, randf_range(0.022, 0.036), GlyphSwarm.Mode.CONVERGE, target, 22.0)
		if t >= dur:
			dissolve_progress = 0.0
			overdrive = 0.0
			_op = {}


func _token_color(r: float) -> Color:
	if r > 0.97:
		return Color(1.0, 0.55, 0.1)
	var c := Color(0.0, 0.85, 1.0).lerp(Color(0.55, 0.2, 1.0), clampf(r * 1.3 - 0.3, 0.0, 1.0))
	return c.lerp(Color(0.9, 1.0, 1.0), clampf(1.0 - r * 4.0, 0.0, 1.0))


# --------------------------------------------------------------- process ---
func _process(delta: float) -> void:
	var hp := hips_world()
	if delta > 0.0:
		_hips_vel = _hips_vel.lerp((hp - _prev_hips) / delta, 0.5)
	_prev_hips = hp

	if is_dodging:
		_dodge_t += delta
		var win: Vector2 = DODGE_WINDOW["sprint" if _dodge_kind.begins_with("sprint") else "stand"]
		var active := _dodge_t >= win.x * 0.6 and _dodge_t <= win.y
		var k := clampf(inverse_lerp(win.x * 0.6, win.y, _dodge_t), 0.0, 1.0)
		var env := sin(k * PI) if active else 0.0
		glitch = env * 0.8
		overdrive = env * 0.6
		for tr in _trails:
			tr.emitting = active
		_wake.emitting = active
		if active:
			_ghost_timer -= delta
			if _ghost_timer <= 0.0:
				_ghost_timer = 0.065
				spawn_afterimage(0.45 + 0.4 * float(_ghost_count % 4) / 3.0, 0.6)
				_ghost_count += 1
			# shed glyphs off the body
			var speed := _hips_vel.length()
			var n := int(clampf(speed * 4.0, 2.0, 40.0))
			for i in n:
				var mesh_i := randi() % _skin_data.size()
				var vi := randi() % (_skin_data[mesh_i].verts as PackedVector3Array).size()
				var wp := skinned_world(mesh_i, vi)
				var vel := -_hips_vel * randf_range(0.05, 0.25) + Vector3(randf_range(-0.3, 0.3), randf_range(0.0, 0.5), randf_range(-0.3, 0.3))
				swarm.emit(wp, vel, _token_color(randf()), randf_range(0.5, 1.1), randf_range(0.02, 0.035), GlyphSwarm.Mode.DRIFT, Vector3.ZERO, 16.0)

	for i in range(_ghosts.size() - 1, -1, -1):
		var g: Dictionary = _ghosts[i]
		g.t += delta
		var life: float = 1.0 - g.t / g.len
		if life <= 0.0:
			g.node.queue_free()
			_ghosts.remove_at(i)
		else:
			(g.mat as ShaderMaterial).set_shader_parameter("life", life)

	_process_op(delta)
