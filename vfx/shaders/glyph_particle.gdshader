// ---------------------------------------------------------------------------
// glyph_particle.gdshader
// Camera-facing glyph sprites for the CPU-simulated GlyphSwarm (MultiMesh).
// Per instance:
//   COLOR            rgb = tint, a = opacity
//   INSTANCE_CUSTOM  x = glyph seed, y = normalised age (0..1),
//                    z = scramble rate, w = stretch (velocity streak)
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform float brightness = 1.35;

varying vec4 v_custom;
varying vec4 v_color;

void vertex() {
	v_custom = INSTANCE_CUSTOM;
	v_color = COLOR;
	// billboard, keep per-instance scale
	float sx = length(MODEL_MATRIX[0].xyz);
	float sy = length(MODEL_MATRIX[1].xyz);
	vec3 world_center = MODEL_MATRIX[3].xyz;
	vec3 right = INV_VIEW_MATRIX[0].xyz;
	vec3 up = INV_VIEW_MATRIX[1].xyz;
	vec3 wp = world_center + right * VERTEX.x * sx + up * VERTEX.y * sy;
	POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(wp, 1.0);
}

void fragment() {
	float seed = v_custom.x;
	float age = v_custom.y;
	float rate = v_custom.z;
	int s = int(seed * 65535.0);
	float idx = token_index(ivec3(s, 11, 5), TIME + seed * 10.0, rate);
	vec3 g = glyph_sample(idx, UV, UV);
	// pop-in then decay; glyph flickers as it dies
	float fade = smoothstep(0.0, 0.08, age) * (1.0 - smoothstep(0.55, 1.0, age));
	float flicker = mix(1.0, step(0.35, hash_f1(floor(TIME * 30.0) + seed * 91.0)), smoothstep(0.6, 0.9, age));
	vec3 col = v_color.rgb;
	ALBEDO = (col * g.x * 1.6 + col * g.y * 0.35) * fade * flicker * v_color.a * brightness;
}
