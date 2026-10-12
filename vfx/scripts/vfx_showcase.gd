## Showcase / test bed for the LLM text VFX.
## Builds the whole stage in code and plays a scripted timeline:
##   boot (reassemble from text) -> dodges with text trails -> collapse into the
##   orb -> orb flight -> unfold back into the body -> disintegrate.
##
## Interactive keys (any key press switches to manual mode):
##   1/2  standing dodge right/left     3/4  sprint dodge right/left
##   Q    orb form on/off               E    disintegrate / reassemble
##   arrows / WASD  move the orb         R    restart the showcase
##
## Render the showcase to frames:
##   godot --rendering-driver opengl3 --write-movie out/frame.png --fixed-fps 30 \
##         --resolution 1280x720 -- --showcase-once
extends Node

const MONO_FONTS: Array[String] = ["DejaVu Sans Mono", "Liberation Mono", "monospace"]

var viewport: SubViewport
var container: SubViewportContainer
var post_mat: ShaderMaterial
var world: Node3D
var fx_root: Node3D
var camera: Camera3D
var floor_mat: ShaderMaterial
var swarm: GlyphSwarm
var character: LlmCharacterVfx
var orb: LlmOrb
var caption: Label
var sub_caption: Label

var t := 0.0
var manual := false
var once := false
var impact := 0.0
var push_dir := Vector2.RIGHT
var in_orb := false

var _events: Array = []
var _event_i := 0
var _cam_keys: Array = []
var _focus := Vector3(0, 0.8, 0)
var _focus_target := "character"
var _orb_path: Array = []  # [time, pos] keys while in orb flight
var _ripple_flip := false
var _caption_full := ""
var _caption_t := 0.0
var _orb_vel := Vector3.ZERO
var _orb_prev := Vector3.ZERO


func _ready() -> void:
	once = "--showcase-once" in OS.get_cmdline_user_args()
	_build_stage()
	_build_timeline()
	# --start=T jumps into the timeline (for iterating on a single beat)
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--start="):
			t = float(a.get_slice("=", 1))
			character.dissolve_progress = 0.0
			while _event_i < _events.size() and _events[_event_i][0] < t:
				_event_i += 1


# ================================================================== stage ===
func _build_stage() -> void:
	container = SubViewportContainer.new()
	container.stretch = true
	container.set_anchors_preset(Control.PRESET_FULL_RECT)
	post_mat = ShaderMaterial.new()
	post_mat.shader = preload("res://vfx/shaders/post_glitch.gdshader")
	container.material = post_mat
	add_child(container)
	viewport = SubViewport.new()
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.use_hdr_2d = false
	container.add_child(viewport)

	world = Node3D.new()
	viewport.add_child(world)
	fx_root = Node3D.new()
	fx_root.name = "Fx"
	world.add_child(fx_root)

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.006, 0.008, 0.016)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.32, 0.38, 0.55)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.glow_enabled = true
	env.glow_intensity = 0.65
	env.glow_strength = 1.0
	env.glow_bloom = 0.05
	env.glow_hdr_threshold = 1.0
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SCREEN
	for i in 7:
		env.set_glow_level(i, 1.0 if i in [1, 2, 3, 4] else 0.0)
	env.fog_enabled = true
	env.fog_light_color = Color(0.02, 0.04, 0.08)
	env.fog_density = 0.09
	var we := WorldEnvironment.new()
	we.environment = env
	world.add_child(we)

	var key := DirectionalLight3D.new()
	key.light_color = Color(0.85, 0.9, 1.0)
	key.light_energy = 1.1
	key.rotation_degrees = Vector3(-42, 28, 0)
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 12.0
	world.add_child(key)
	var rim := DirectionalLight3D.new()
	rim.light_color = Color(0.2, 0.7, 1.0)
	rim.light_energy = 1.6
	rim.rotation_degrees = Vector3(-15, 200, 0)
	rim.light_cull_mask = 1  # keep the back light's glint off the glossy floor
	world.add_child(rim)

	var floor_mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(120, 120)
	floor_mi.mesh = pm
	floor_mi.layers = 2
	floor_mat = ShaderMaterial.new()
	floor_mat.shader = preload("res://vfx/shaders/data_floor.gdshader")
	floor_mat.set_shader_parameter("glyph_atlas", preload("res://vfx/textures/glyph_atlas.png"))
	floor_mi.material_override = floor_mat
	world.add_child(floor_mi)

	swarm = GlyphSwarm.new()
	world.add_child(swarm)

	character = LlmCharacterVfx.new()
	character.swarm = swarm
	character.fx_root = fx_root
	world.add_child(character)
	character.dodge_started.connect(_on_dodge_started)
	character.dodge_finished.connect(_on_dodge_finished)

	orb = LlmOrb.new()
	orb.swarm = swarm
	orb.fx_root = fx_root
	world.add_child(orb)
	orb.position = Vector3(0, 0.95, 0)
	swarm.attractor = orb

	camera = Camera3D.new()
	camera.fov = 42.0
	camera.near = 0.05
	world.add_child(camera)

	var font := SystemFont.new()
	font.font_names = PackedStringArray(MONO_FONTS)
	caption = Label.new()
	caption.add_theme_font_override("font", font)
	caption.add_theme_font_size_override("font_size", 22)
	caption.add_theme_color_override("font_color", Color(0.55, 0.95, 1.0))
	caption.position = Vector2(36, 26)
	add_child(caption)
	sub_caption = Label.new()
	sub_caption.add_theme_font_override("font", font)
	sub_caption.add_theme_font_size_override("font_size", 15)
	sub_caption.add_theme_color_override("font_color", Color(0.45, 0.55, 0.85, 0.85))
	sub_caption.position = Vector2(38, 58)
	add_child(sub_caption)


# =============================================================== timeline ===
func _build_timeline() -> void:
	t = 0.0
	_event_i = 0
	in_orb = false
	_focus_target = "character"
	character.position = Vector3.ZERO
	character.rotation = Vector3.ZERO
	character.dissolve_progress = 1.0
	character.visible = true
	orb.form = 0.0
	_events = [
		[0.0, func(): _say("> boot(model=\"ch_02\")", "reassembling weights from token stream ..."); character.reassemble(2.2, Vector3.DOWN)],
		[2.6, func(): _say("> idle()", "data-skin // inference scan")],
		[3.4, func(): _say("> dodge(\"stand_r\")", "afterimages + token ribbons + glitch slicing"); character.dodge("stand_r")],
		[4.7, func(): _say("> dodge(\"stand_l\")", "afterimages + token ribbons + glitch slicing"); character.dodge("stand_l")],
		[5.35, func(): create_tween().tween_property(character, "rotation_degrees:y", 90.0, 0.4).set_trans(Tween.TRANS_SINE)],
		[6.0, func(): _say("> dodge(\"sprint_r\")", "aerial dodge, wake sheet"); character.dodge("sprint_r")],
		[7.5, func(): _say("> compress(body) -> orb", "detokenizing toward the context core"); _start_orb()],
		[9.3, func(): _say("> orb.traverse()", "")],
		[12.6, func(): _say("> expand(orb) -> body", "decoding ..."); _end_orb()],
		[14.6, func(): _say("> idle()", "")],
		[15.4, func(): _say("> disintegrate()", "streaming out ..."); character.disintegrate(2.4, Vector3.UP, Vector3(0.8, 0.0, -0.4))],
		[18.4, func(): _say("> eos", "")],
		[19.2, func(): _finish()],
	]
	# camera keys: time, yaw(deg), distance, height, look-height offset, fov
	_cam_keys = [
		[0.0, 18.0, 3.0, 0.15, 0.0, 40.0],
		[2.6, -10.0, 3.3, 0.1, 0.0, 40.0],
		[3.3, 0.0, 3.4, 0.2, -0.05, 42.0],
		[5.4, 10.0, 3.4, 0.25, -0.05, 42.0],
		[5.9, -12.0, 5.6, 0.35, -0.1, 44.0],
		[7.3, 60.0, 3.6, 0.3, 0.05, 42.0],
		[9.2, 35.0, 3.4, 0.25, 0.0, 44.0],
		[12.4, -20.0, 3.2, 0.2, 0.0, 44.0],
		[14.6, 20.0, 3.2, 0.1, 0.0, 40.0],
		[19.2, 35.0, 3.6, 0.35, 0.0, 40.0],
	]


func _finish() -> void:
	if once:
		get_tree().quit()
	else:
		swarm.clear()
		_build_timeline()


func _start_orb() -> void:
	in_orb = true
	orb.global_position = character.chest_world() + Vector3(0, 0.05, 0)
	_orb_prev = orb.global_position
	character.collapse_to_orb(orb, 1.5)
	var tw := create_tween()
	tw.tween_interval(0.25)
	tw.tween_property(orb, "form", 1.0, 1.3).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_kick(0.6, Vector2.UP)
	_ripple(character.global_position)
	var start := orb.global_position
	var g := character.global_position
	# orb flight path (absolute times), smooth-interpolated in _update_orb
	_orb_path = [
		[7.5, start], [9.0, start + Vector3(0, 0.35, 0)],
		[10.0, g + Vector3(1.2, 1.5, 0.6)], [10.7, g + Vector3(2.2, 1.0, -0.6)],
		[11.0, g + Vector3(-1.4, 0.9, -0.2)],  # zip
		[11.9, g + Vector3(-0.6, 1.3, 0.8)], [12.6, g + Vector3(0.0, 1.0, 0.4)],
	]
	_focus_target = "orb"


func _end_orb() -> void:
	# stand the body back up under the orb, facing the camera
	var p := orb.global_position
	character.global_position = Vector3(p.x, 0.0, p.z) - Vector3(0, 0, 0.03)
	character.rotation_degrees.y = 0.0
	character.unfold_from_orb(orb, 1.6)
	var tw := create_tween()
	tw.tween_interval(0.4)
	tw.tween_property(orb, "form", 0.0, 1.2).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	tw.tween_callback(func(): in_orb = false)
	_kick(0.5, Vector2.DOWN)
	_ripple(character.global_position)
	_focus_target = "character"


func _say(main: String, sub: String) -> void:
	_caption_full = main
	_caption_t = 0.0
	sub_caption.text = sub


func _kick(amount: float, dir: Vector2) -> void:
	impact = maxf(impact, amount)
	push_dir = dir


func _ripple(at: Vector3) -> void:
	_ripple_flip = not _ripple_flip
	floor_mat.set_shader_parameter("ripple0" if _ripple_flip else "ripple1", Vector4(at.x, at.y, at.z, t))


func _on_dodge_started(kind: String) -> void:
	_kick(0.85, Vector2.LEFT if kind.ends_with("_r") else Vector2.RIGHT)
	_ripple(character.hips_world())


func _on_dodge_finished(_kind: String) -> void:
	_ripple(character.hips_world())


# ================================================================ process ===
func _process(delta: float) -> void:
	t += delta
	if not manual:
		while _event_i < _events.size() and t >= _events[_event_i][0]:
			var cb: Callable = _events[_event_i][1]
			_event_i += 1
			cb.call()
		_update_orb_path()
	else:
		_manual_orb_move(delta)

	# orb charge from speed
	var ov := (orb.global_position - _orb_prev) / maxf(delta, 1e-4)
	_orb_prev = orb.global_position
	_orb_vel = _orb_vel.lerp(ov, 0.3)
	orb.charge = clampf((_orb_vel.length() - 1.0) / 6.0, 0.0, 1.0)
	if orb.charge > 0.5:
		_kick(orb.charge * 0.5, Vector2(_orb_vel.x, -_orb_vel.y))

	# focus + camera
	var ft := orb.global_position if _focus_target == "orb" else character.hips_world() + Vector3(0, 0.05, 0)
	_focus = _focus.lerp(ft, 1.0 - exp(-delta * 6.0))
	_update_camera()

	impact = maxf(0.0, impact - delta * 2.2)
	post_mat.set_shader_parameter("impact", impact)
	post_mat.set_shader_parameter("push_dir", push_dir)
	floor_mat.set_shader_parameter("now", t)
	floor_mat.set_shader_parameter("focus", orb.global_position if in_orb else character.hips_world())
	floor_mat.set_shader_parameter("focus_glow", 1.6 if in_orb else 1.0)

	_caption_t += delta
	var n := mini(_caption_full.length(), int(_caption_t * 38.0))
	var cursor := "█" if fmod(t, 0.6) < 0.3 else " "
	caption.text = _caption_full.substr(0, n) + cursor


func _update_orb_path() -> void:
	if _orb_path.is_empty() or not in_orb:
		return
	if t < _orb_path[0][0] or t > _orb_path[_orb_path.size() - 1][0]:
		return
	for i in _orb_path.size() - 1:
		var a = _orb_path[i]
		var b = _orb_path[i + 1]
		if t >= a[0] and t <= b[0]:
			var k: float = (t - a[0]) / (b[0] - a[0])
			var p0: Vector3 = _orb_path[maxi(i - 1, 0)][1]
			var p3: Vector3 = _orb_path[mini(i + 2, _orb_path.size() - 1)][1]
			orb.global_position = Vector3(
				_catmull(p0.x, a[1].x, b[1].x, p3.x, k),
				_catmull(p0.y, a[1].y, b[1].y, p3.y, k),
				_catmull(p0.z, a[1].z, b[1].z, p3.z, k))
			orb.global_position.y += sin(t * 3.0) * 0.03
			return


func _catmull(p0: float, p1: float, p2: float, p3: float, k: float) -> float:
	var k2 := k * k
	var k3 := k2 * k
	return 0.5 * ((2.0 * p1) + (-p0 + p2) * k + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * k2 + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * k3)


func _update_camera() -> void:
	if _cam_keys.is_empty():
		return
	var a: Array = _cam_keys[0]
	var b: Array = a
	for i in _cam_keys.size():
		if _cam_keys[i][0] <= t:
			a = _cam_keys[i]
			b = _cam_keys[mini(i + 1, _cam_keys.size() - 1)]
	var k := 0.0
	if b[0] > a[0]:
		k = clampf((t - a[0]) / (b[0] - a[0]), 0.0, 1.0)
		k = k * k * (3.0 - 2.0 * k)
	var yaw := deg_to_rad(lerpf(a[1], b[1], k))
	var dist := lerpf(a[2], b[2], k)
	var h := lerpf(a[3], b[3], k)
	var look_off := lerpf(a[4], b[4], k)
	camera.fov = lerpf(a[5], b[5], k)
	var shake := Vector3(randf_range(-1, 1), randf_range(-1, 1), 0) * impact * 0.02
	var pos := _focus + Vector3(sin(yaw) * dist, h, cos(yaw) * dist) + shake
	camera.look_at_from_position(pos, _focus + Vector3(0, look_off, 0))


# ================================================================== input ===
func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	var k: Key = event.keycode
	if k == KEY_R:
		manual = false
		swarm.clear()
		_build_timeline()
		return
	manual = true
	match k:
		KEY_1: if not in_orb: character.dodge("stand_r")
		KEY_2: if not in_orb: character.dodge("stand_l")
		KEY_3: if not in_orb: character.dodge("sprint_r")
		KEY_4: if not in_orb: character.dodge("sprint_l")
		KEY_Q:
			if character.is_busy():
				return
			if in_orb:
				_end_orb()
			else:
				_orb_path = []
				_start_orb()
		KEY_E:
			if in_orb or character.is_busy():
				return
			if character.dissolve_progress > 0.5:
				character.reassemble(1.8, Vector3.DOWN)
			else:
				character.disintegrate(2.0, Vector3.UP, Vector3(0.8, 0.0, -0.4))


func _manual_orb_move(delta: float) -> void:
	if not in_orb or orb.form < 0.9:
		return
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_LEFT) or Input.is_key_pressed(KEY_A): dir.x -= 1
	if Input.is_key_pressed(KEY_RIGHT) or Input.is_key_pressed(KEY_D): dir.x += 1
	if Input.is_key_pressed(KEY_UP) or Input.is_key_pressed(KEY_W): dir.z -= 1
	if Input.is_key_pressed(KEY_DOWN) or Input.is_key_pressed(KEY_S): dir.z += 1
	var basis := Basis(Vector3.UP, camera.global_rotation.y)
	orb.global_position += basis * dir.normalized() * 3.0 * delta
