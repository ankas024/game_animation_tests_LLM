## CPU-simulated swarm of glyph sprites rendered through one MultiMesh.
## Every particle is a "token" that has detached from the body. Modes:
##   DRIFT    - blown away: buoyancy + swirling turbulence + drag
##   ATTRACT  - sucked into `attractor` along a spiral, dies on arrival
##   CONVERGE - flies from its spawn point to a fixed target, arriving exactly
##              at the end of its life (used to re-assemble the body)
##   ORBIT    - circles `attractor` on a tilted orbit (orb ambience)
class_name GlyphSwarm
extends Node3D

enum Mode { DRIFT, ATTRACT, CONVERGE, ORBIT }

@export var max_particles := 6000
@export var buoyancy := 0.6
@export var drag := 1.6
@export var turbulence := 1.4
@export var attract_strength := 30.0

var attractor: Node3D

var _mm: MultiMesh
var _mmi: MultiMeshInstance3D
var _buf: PackedFloat32Array
var _pos: PackedVector3Array
var _vel: PackedVector3Array
var _start: PackedVector3Array
var _target: PackedVector3Array
var _age: PackedFloat32Array
var _life: PackedFloat32Array
var _size: PackedFloat32Array
var _seed: PackedFloat32Array
var _rate: PackedFloat32Array
var _mode: PackedInt32Array
var _col: PackedColorArray
var _alive: PackedByteArray
var _next := 0
var _time := 0.0

const STRIDE := 20


func _ready() -> void:
	top_level = true
	global_transform = Transform3D.IDENTITY
	_mm = MultiMesh.new()
	_mm.transform_format = MultiMesh.TRANSFORM_3D
	_mm.use_colors = true
	_mm.use_custom_data = true
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	_mm.mesh = quad
	_mm.instance_count = max_particles
	_mmi = MultiMeshInstance3D.new()
	_mmi.multimesh = _mm
	_mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mmi.custom_aabb = AABB(Vector3(-60, -10, -60), Vector3(120, 40, 120))
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://vfx/shaders/glyph_particle.gdshader")
	mat.set_shader_parameter("glyph_atlas", preload("res://vfx/textures/glyph_atlas.png"))
	_mmi.material_override = mat
	add_child(_mmi)

	_buf.resize(max_particles * STRIDE)
	for arr in [_pos, _vel, _start, _target, _col]:
		arr.resize(max_particles)
	for arr in [_age, _life, _size, _seed, _rate, _mode, _alive]:
		arr.resize(max_particles)


func emit(pos: Vector3, vel: Vector3, color: Color, life: float, size: float,
		mode: int = Mode.DRIFT, target := Vector3.ZERO, rate := 12.0) -> void:
	var i := _next
	_next = (_next + 1) % max_particles
	_pos[i] = pos
	_start[i] = pos
	_vel[i] = vel
	_col[i] = color
	_life[i] = maxf(life, 0.01)
	_age[i] = 0.0
	_size[i] = size
	_seed[i] = randf()
	_rate[i] = rate
	_mode[i] = mode
	_target[i] = target
	_alive[i] = 1


func clear() -> void:
	_alive.fill(0)


func _process(delta: float) -> void:
	_time += delta
	var att := attractor.global_position if is_instance_valid(attractor) else Vector3.ZERO
	var t := _time
	var damp := exp(-drag * delta)
	for i in max_particles:
		var o := i * STRIDE
		if _alive[i] == 0:
			_buf[o] = 0.0; _buf[o + 5] = 0.0; _buf[o + 10] = 0.0
			_buf[o + 15] = 0.0
			continue
		_age[i] += delta
		var a := _age[i] / _life[i]
		if a >= 1.0:
			_alive[i] = 0
			_buf[o] = 0.0; _buf[o + 5] = 0.0; _buf[o + 10] = 0.0
			_buf[o + 15] = 0.0
			continue
		var p := _pos[i]
		var v := _vel[i]
		var fade_mul := 1.0
		match _mode[i]:
			Mode.DRIFT:
				var s := _seed[i] * 6.28
				var turb := Vector3(
					sin(p.y * 3.1 + t * 1.7 + s), sin(p.z * 2.7 + t * 1.3 + s * 1.3) * 0.6,
					cos(p.x * 2.9 + t * 1.9 + s))
				v += (Vector3.UP * buoyancy + turb * turbulence) * delta
				v *= damp
				p += v * delta
			Mode.ATTRACT:
				var to := att - p
				var d := to.length()
				if d < 0.1:
					_alive[i] = 0
					_buf[o] = 0.0; _buf[o + 5] = 0.0; _buf[o + 10] = 0.0
					_buf[o + 15] = 0.0
					continue
				var dir := to / d
				# spiral in (not a stable accretion disk): swirl fades as the glyph ages
				var swirl := dir.cross(Vector3.UP).normalized() * 1.6 * (1.0 - a)
				v += (dir * attract_strength * (0.6 + a * 1.5) + swirl) * delta
				v *= exp(-3.2 * delta)
				p += v * delta
				a = maxf(a, 0.2) # stay bright while travelling
				fade_mul = clampf((d - 0.1) / 0.35, 0.0, 1.0) # dim as it sinks into the core
			Mode.CONVERGE:
				var e := a * a * (3.0 - 2.0 * a)
				var arc := sin(a * PI) * 0.35
				var side := (_target[i] - _start[i]).cross(Vector3.UP).normalized()
				p = _start[i].lerp(_target[i], e) + (side * cos(_seed[i] * 6.28) + Vector3.UP * sin(_seed[i] * 6.28)) * arc
				a = 0.25 + a * 0.3 # keep the glyph lit until it lands
			Mode.ORBIT:
				var r := _target[i].x
				var tilt := _target[i].y
				var ang := _seed[i] * TAU + _age[i] * _target[i].z
				var q := Vector3(cos(ang) * r, 0.0, sin(ang) * r).rotated(Vector3(1, 0, 0.3).normalized(), tilt)
				p = att + q
		_pos[i] = p
		_vel[i] = v
		var sz := _size[i]
		_buf[o] = sz; _buf[o + 1] = 0.0; _buf[o + 2] = 0.0; _buf[o + 3] = p.x
		_buf[o + 4] = 0.0; _buf[o + 5] = sz; _buf[o + 6] = 0.0; _buf[o + 7] = p.y
		_buf[o + 8] = 0.0; _buf[o + 9] = 0.0; _buf[o + 10] = sz; _buf[o + 11] = p.z
		var c := _col[i]
		_buf[o + 12] = c.r; _buf[o + 13] = c.g; _buf[o + 14] = c.b; _buf[o + 15] = c.a * fade_mul
		_buf[o + 16] = _seed[i]; _buf[o + 17] = a; _buf[o + 18] = _rate[i]; _buf[o + 19] = 0.0
	_mm.buffer = _buf
