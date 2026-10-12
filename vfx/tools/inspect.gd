extends SceneTree
func _init():
	for p in ["res://assets/animations/combat/dodge/A_Dodge_Stand_R.fbx","res://assets/animations/combat/dodge/A_Dodge_Sprint_R.fbx","res://assets/animations/idle/A_ch02_Idle_Loop.fbx"]:
		var root = load(p).instantiate()
		print("== ", p)
		_dump(root, 0)
	quit()
func _dump(n: Node, d: int):
	var s = "  ".repeat(d) + n.name + " <" + n.get_class() + ">"
	if n is MeshInstance3D: s += " verts?"
	if n is Skeleton3D: s += " bones=%d" % n.get_bone_count()
	if n is AnimationPlayer:
		for a in n.get_animation_list():
			var an: Animation = n.get_animation(a)
			s += "\n   anim '%s' len=%.3f tracks=%d" % [a, an.length, an.get_track_count()]
			for t in min(3, an.get_track_count()): s += "\n     " + str(an.track_get_path(t)) + " type=" + str(an.track_get_type(t)) + " keys=" + str(an.track_get_key_count(t))
			var hi = an.find_track(NodePath("Armature/Skeleton3D:mixamorig_Hips"), Animation.TYPE_POSITION_3D)
			if hi >= 0: s += "\n     hips pos first=%s last=%s" % [an.track_get_key_value(hi,0), an.track_get_key_value(hi, an.track_get_key_count(hi)-1)]
	print(s)
	for c in n.get_children(): _dump(c, d+1)
