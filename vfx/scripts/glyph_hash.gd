## CPU mirror of the integer hash + dissolve field in glyph_common.gdshaderinc /
## llm_character.gdshader. Keeping these bit-identical lets the CPU know the exact
## moment a voxel of the body is "detokenized", so particles spawn right there.
class_name GlyphHash

const MASK := 0xFFFFFFFF


static func pcg(v: int) -> int:
	var state := (v * 747796405 + 2891336453) & MASK
	var word := ((((state >> ((state >> 28) + 4)) ^ state) & MASK) * 277803737) & MASK
	return ((word >> 22) ^ word) & MASK


static func hash_i3(x: int, y: int, z: int) -> float:
	var hz := pcg(z & MASK)
	var hy := pcg(((y & MASK) + hz) & MASK)
	var h := pcg(((x & MASK) + hy) & MASK)
	return float(h) / 4294967295.0


## Same maths as dissolve_field() in llm_character.gdshader.
static func dissolve_field(p: Vector3, origin: Vector3, axis: Vector3, extent: float,
		radial: float, noise: float, voxel: float) -> float:
	var d := p - origin
	var lin := d.dot(axis) / extent
	var rad := 1.0 - d.length() / extent
	var h := lerpf(lin, rad, radial)
	var n := hash_i3(floori(p.x / voxel), floori(p.y / voxel), floori(p.z / voxel))
	return clampf(lerpf(h, n, noise), 0.0, 1.0)
