// ---------------------------------------------------------------------------
// data_floor.gdshader
// Dark glass floor: fine grid, faint "embedding space" text in the cells,
// a glow pool under the character and shockwave rings on dash events.
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform vec3 focus = vec3(0.0);           // world position of the character / orb
uniform float focus_glow = 1.0;
uniform vec4 ripple0 = vec4(0.0, 0.0, 0.0, -10.0); // xyz = origin, w = start time
uniform vec4 ripple1 = vec4(0.0, 0.0, 0.0, -10.0);
uniform float now = 0.0;
uniform float grid = 0.5;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float ripple(vec4 r) {
	float age = now - r.w;
	if (age < 0.0 || age > 1.6) return 0.0;
	float d = distance(wpos.xz, r.xz);
	float radius = age * 4.5;
	return exp(-pow((d - radius) / 0.035, 2.0)) * pow(1.0 - age / 1.6, 2.0);
}

void fragment() {
	vec2 g = wpos.xz / grid;
	vec2 gf = abs(fract(g - 0.5) - 0.5) / fwidth(g);
	float line = 1.0 - min(min(gf.x, gf.y), 1.0);
	vec2 g2 = wpos.xz / (grid * 4.0);
	vec2 gf2 = abs(fract(g2 - 0.5) - 0.5) / fwidth(g2);
	float line2 = 1.0 - min(min(gf2.x, gf2.y), 1.0);

	float d = distance(wpos.xz, focus.xz);
	float pool = exp(-d * d * 0.9) * focus_glow;
	float far_fade = exp(-length(wpos.xz) * 0.12);

	// faint text living in the floor cells, denser near the focus
	ivec3 cell;
	vec3 t = text_plane(wpos.xz / 0.09, TIME, 2.0, 120, 1.5, cell);
	float txt = t.x * (0.05 + 0.6 * pool) * step(0.55, hash_i3(cell));

	float rip = ripple(ripple0) + ripple(ripple1);
	vec3 c = llm_palette(0.62);
	ALBEDO = vec3(0.012, 0.014, 0.025);
	ROUGHNESS = 0.32;
	METALLIC = 0.0;
	SPECULAR = 0.0;
	EMISSION = (c * (line * 0.07 + line2 * 0.12) * far_fade
		+ c * txt * 0.9
		+ c * pool * 0.08
		+ llm_palette(0.7) * rip * 1.1);
}
