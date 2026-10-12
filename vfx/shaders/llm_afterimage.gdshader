// ---------------------------------------------------------------------------
// llm_afterimage.gdshader
// Dash afterimages: a frozen copy of the pose rendered purely as text.
// The silhouette is a fresnel outline filled with streaming glyph rows; as
// `life` runs out the copy smears along the dash direction, its rows shear
// apart and it is "garbage collected" voxel by voxel.
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back, shadows_disabled;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform float life : hint_range(0.0, 1.0) = 1.0;
uniform float hue : hint_range(0.0, 1.0) = 0.6;          // palette position for this ghost
uniform vec3 smear_dir = vec3(-1.0, 0.0, 0.0);           // model space, opposite to motion
uniform float smear_amount = 0.35;
uniform float glyph_size = 0.026;
uniform float voxel_size = 0.03;
uniform float intensity = 0.85;

varying vec3 rest_pos;
varying vec3 rest_nrm;

void vertex() {
	rest_pos = CUSTOM0.xyz;
	rest_nrm = NORMAL;
	float age = 1.0 - life;
	// rows shear apart: each 3cm slice lags behind by a random amount
	float slice = floor(rest_pos.y / 0.03);
	float lag = hash_i3(ivec3(int(slice), 5, 77));
	VERTEX += normalize(smear_dir) * age * age * smear_amount * (0.3 + lag * 1.4);
	// and the whole thing inflates a hair, like a signal decaying
	VERTEX += NORMAL * age * 0.015;
}

void fragment() {
	float age = 1.0 - life;
	// garbage collection: voxels drop out as the ghost ages
	float vox = hash_i3(ivec3(floor(rest_pos / voxel_size)));
	if (vox < age * 1.05 - 0.05) {
		discard;
	}
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 2.0);

	vec3 n = rest_nrm;
	vec3 w = pow(abs(n), vec3(6.0));
	w /= (w.x + w.y + w.z + 1e-5);
	vec3 s = rest_pos / glyph_size;
	ivec3 c0; ivec3 c1; ivec3 c2;
	vec3 tx = text_plane(vec2(s.z * 0.8, s.y), TIME, 14.0, 3, 6.0, c0);
	vec3 ty = text_plane(vec2(s.x * 0.8, s.z), TIME, 14.0, 4, 6.0, c1);
	vec3 tz = text_plane(vec2(s.x * 0.8, s.y), TIME, 14.0, 5, 6.0, c2);
	float glyph = tx.x * w.x + ty.x * w.y + tz.x * w.z;
	float halo = tx.y * w.x + ty.y * w.y + tz.y * w.z;

	// horizontal scanlines (CRT feel)
	float scan = 0.65 + 0.35 * sin(FRAGCOORD.y * 1.6 + TIME * 40.0);

	vec3 col = llm_palette(hue + 0.25 * fres);
	float body = glyph * 1.3 + halo * 0.12 + fres * 0.55;
	ALBEDO = col * body * scan * intensity * life;
	// near-front cells flare white as they are collected
	float flare = smoothstep(age * 1.05 - 0.05, age * 1.05 + 0.02, vox);
	ALBEDO += col * (1.0 - flare) * 1.2 * life;
}
