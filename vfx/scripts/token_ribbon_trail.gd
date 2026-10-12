## A ribbon of streaming text that follows a node.
##  FACE_CAMERA - billboarded strip (limb / orb trails)
##  SHEET       - vertical sheet of fixed height (the body "wake" during dashes)
## Text is anchored to the world: each point remembers the distance travelled
## when it was emitted, which becomes UV.x in metres.
class_name TokenRibbonTrail
extends MeshInstance3D

enum Orient { FACE_CAMERA, SHEET }

@export var target: Node3D
@export var orient: Orient = Orient.FACE_CAMERA
@export var width := 0.08
@export var lifetime := 0.45
@export var min_step := 0.025
@export var emitting := false
@export var taper := true
@export var sheet_offset := Vector3.ZERO  # sheet centre relative to target (world)

var shader_material: ShaderMaterial

var _pts: Array[Vector3] = []
var _age: Array[float] = []
var _dist: Array[float] = []
var _total := 0.0
var _imesh: ImmediateMesh


func _init() -> void:
	shader_material = ShaderMaterial.new()
	shader_material.shader = preload("res://vfx/shaders/token_ribbon.gdshader")
	shader_material.set_shader_parameter("glyph_atlas", preload("res://vfx/textures/glyph_atlas.png"))


func _ready() -> void:
	top_level = true
	global_transform = Transform3D.IDENTITY
	_imesh = ImmediateMesh.new()
	mesh = _imesh
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	extra_cull_margin = 16384.0
	shader_material.set_shader_parameter("ribbon_width", width)


func set_param(p: String, v: Variant) -> void:
	shader_material.set_shader_parameter(p, v)


func _head_pos() -> Vector3:
	return target.global_position + sheet_offset


func _process(delta: float) -> void:
	for i in _age.size():
		_age[i] += delta
	while _age.size() > 0 and _age[0] >= lifetime:
		_pts.pop_front(); _age.pop_front(); _dist.pop_front()

	if emitting and is_instance_valid(target):
		var hp := _head_pos()
		if _pts.is_empty():
			_push(hp)
		else:
			var last := _pts[_pts.size() - 1]
			var d := hp.distance_to(last)
			if d >= min_step:
				_total += d
				_push(hp)
	_rebuild()


func _push(p: Vector3) -> void:
	_pts.append(p)
	_age.append(0.0)
	_dist.append(_total)


func _rebuild() -> void:
	_imesh.clear_surfaces()
	var pts := _pts.duplicate()
	var ages := _age.duplicate()
	var dists := _dist.duplicate()
	if emitting and is_instance_valid(target) and not pts.is_empty():
		# live head so the ribbon stays glued to its target between steps
		var hp := _head_pos()
		pts.append(hp)
		ages.append(0.0)
		dists.append(_total + hp.distance_to(pts[pts.size() - 2]))
	var n := pts.size()
	if n < 2:
		return
	var cam := get_viewport().get_camera_3d()
	var cam_pos := cam.global_position if cam else Vector3(0, 1, 5)
	var cam_right := cam.global_basis.x if cam else Vector3.RIGHT
	_imesh.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP, shader_material)
	for i in n:
		var p: Vector3 = pts[i]
		var life := 1.0 - float(ages[i]) / lifetime
		var tangent: Vector3
		if i == n - 1:
			tangent = p - pts[i - 1]
		else:
			tangent = pts[i + 1] - p
		if tangent.length_squared() < 1e-10:
			tangent = Vector3.RIGHT
		tangent = tangent.normalized()
		var side: Vector3
		var w := width
		if taper:
			w *= clampf(life * 1.6, 0.0, 1.0)
		if orient == Orient.FACE_CAMERA:
			side = tangent.cross(cam_pos - p).normalized() * w * 0.5
		else:
			side = Vector3.UP * w * 0.5
		var col := Color(1, 1, 1, life)
		# flag segments that run right-to-left on screen so the shader can flip glyphs
		var flip := Vector2(1.0 if tangent.dot(cam_right) < 0.0 and orient == Orient.FACE_CAMERA else 0.0, 0.0)
		_imesh.surface_set_color(col)
		_imesh.surface_set_uv(Vector2(dists[i], 0.0))
		_imesh.surface_set_uv2(flip)
		_imesh.surface_add_vertex(p - side)
		_imesh.surface_set_color(col)
		_imesh.surface_set_uv(Vector2(dists[i], 1.0))
		_imesh.surface_set_uv2(flip)
		_imesh.surface_add_vertex(p + side)
	_imesh.surface_end()
