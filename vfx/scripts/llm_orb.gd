## The orb form: a spinning globe of text around a white-hot core, ringed by
## three orbiting token streams, trailing a ribbon of text and a cloud of
## orbiting glyphs.
class_name LlmOrb
extends Node3D

const ATLAS := preload("res://vfx/textures/glyph_atlas.png")
const ORB_SHADER := preload("res://vfx/shaders/llm_orb.gdshader")
const RIBBON_SHADER := preload("res://vfx/shaders/token_ribbon.gdshader")

@export var swarm: GlyphSwarm
@export var fx_root: Node3D
@export var radius := 0.2

var form := 0.0:
	set(v):
		form = v
		_apply_form()
var charge := 0.0:
	set(v):
		charge = v
		for m in [_shell_mat, _core_mat]:
			if m: m.set_shader_parameter("charge", v)

var trail: TokenRibbonTrail
var _shell_mat: ShaderMaterial
var _core_mat: ShaderMaterial
var _rings: Array[Node3D] = []
var _ring_speeds := [1.9, -1.4, 2.6]
var _light: OmniLight3D
var _visual: Node3D
var _orbit_timer := 0.0
var _t := 0.0


func _ready() -> void:
	_visual = Node3D.new()
	add_child(_visual)

	var shell := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = radius
	sm.height = radius * 2.0
	sm.radial_segments = 64
	sm.rings = 32
	shell.mesh = sm
	_shell_mat = _orb_mat(0)
	shell.material_override = _shell_mat
	_visual.add_child(shell)

	var core := MeshInstance3D.new()
	var cm := SphereMesh.new()
	cm.radius = radius * 0.3
	cm.height = radius * 0.6
	core.mesh = cm
	_core_mat = _orb_mat(1)
	core.material_override = _core_mat
	_visual.add_child(core)

	var specs := [[radius * 1.55, 0.035, Vector3(0.35, 0, 0.2), 0.55],
		[radius * 1.85, 0.03, Vector3(-0.6, 0.4, 0.1), 0.72],
		[radius * 2.2, 0.026, Vector3(1.2, -0.3, 0.5), 0.42]]
	for i in specs.size():
		var pivot := Node3D.new()
		pivot.rotation = specs[i][2]
		_visual.add_child(pivot)
		var ring := MeshInstance3D.new()
		ring.mesh = _ring_mesh(specs[i][0], specs[i][1])
		var rm := ShaderMaterial.new()
		rm.shader = RIBBON_SHADER
		rm.set_shader_parameter("glyph_atlas", ATLAS)
		rm.set_shader_parameter("ribbon_width", specs[i][1])
		rm.set_shader_parameter("hue", specs[i][3])
		rm.set_shader_parameter("core_width", 0.0)
		rm.set_shader_parameter("scroll_speed", 0.0)
		rm.set_shader_parameter("scramble_rate", 6.0)
		rm.set_shader_parameter("intensity", 2.2)
		rm.set_shader_parameter("id_offset", float(i * 3))
		ring.material_override = rm
		ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		pivot.add_child(ring)
		_rings.append(pivot)

	_light = OmniLight3D.new()
	_light.light_color = Color(0.25, 0.8, 1.0)
	_light.omni_range = 4.0
	_light.light_energy = 0.0
	_light.shadow_enabled = false
	add_child(_light)

	trail = TokenRibbonTrail.new()
	trail.target = self
	trail.width = radius * 1.2
	trail.lifetime = 0.7
	trail.min_step = 0.03
	(fx_root if fx_root else get_parent()).add_child.call_deferred(trail)
	trail.set_param("rows", 3.0)
	trail.set_param("hue", 0.6)
	trail.set_param("core_width", 0.05)
	trail.set_param("intensity", 1.1)
	trail.set_param("scroll_speed", 4.0)
	trail.set_param("glyph_fill", 0.8)
	_apply_form()


func _orb_mat(layer: int) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = ORB_SHADER
	m.set_shader_parameter("glyph_atlas", ATLAS)
	m.set_shader_parameter("layer", layer)
	return m


## Flat annulus whose UV.x runs along the circumference in metres, so the
## token_ribbon shader can lay text around it.
func _ring_mesh(r: float, w: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var seg := 96
	var circ := TAU * r
	for i in seg:
		var a0 := TAU * i / seg
		var a1 := TAU * (i + 1) / seg
		var u0 := circ * i / seg
		var u1 := circ * (i + 1) / seg
		var d0 := Vector3(cos(a0), 0, sin(a0))
		var d1 := Vector3(cos(a1), 0, sin(a1))
		var p00 := d0 * (r - w * 0.5); var p01 := d0 * (r + w * 0.5)
		var p10 := d1 * (r - w * 0.5); var p11 := d1 * (r + w * 0.5)
		for v in [[p00, Vector2(u0, 0)], [p01, Vector2(u0, 1)], [p11, Vector2(u1, 1)],
				[p00, Vector2(u0, 0)], [p11, Vector2(u1, 1)], [p10, Vector2(u1, 0)]]:
			st.set_color(Color(1, 1, 1, 1))
			st.set_uv(v[1])
			st.add_vertex(v[0])
	return st.commit()


func _apply_form() -> void:
	if not _visual:
		return
	_visual.visible = form > 0.001
	var s := lerpf(0.2, 1.0, ease(form, 0.4))
	_visual.scale = Vector3.ONE * s
	_shell_mat.set_shader_parameter("form", form)
	_core_mat.set_shader_parameter("form", form)
	for i in _rings.size():
		_rings[i].visible = form > 0.35 + i * 0.15
	_light.light_energy = form * (2.2 + charge * 2.0)
	trail.emitting = form > 0.6


func _process(delta: float) -> void:
	_t += delta
	for i in _rings.size():
		_rings[i].rotate_object_local(Vector3.UP, _ring_speeds[i] * delta * (1.0 + charge * 2.5))
	_visual.rotate_y(delta * 0.6)
	if form > 0.7 and swarm:
		_orbit_timer -= delta
		while _orbit_timer <= 0.0:
			_orbit_timer += 0.012
			var r := randf_range(radius * 1.3, radius * 3.0)
			var data := Vector3(r, randf_range(-1.2, 1.2), randf_range(1.5, 4.0) * (1.0 if randf() > 0.3 else -1.0))
			var col := Color(0.2, 0.9, 1.0) if randf() > 0.2 else Color(0.6, 0.3, 1.0)
			swarm.emit(global_position, Vector3.ZERO, col, randf_range(0.8, 1.6), randf_range(0.02, 0.032), GlyphSwarm.Mode.ORBIT, data, 18.0)
