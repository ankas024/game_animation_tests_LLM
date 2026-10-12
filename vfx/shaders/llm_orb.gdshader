// ---------------------------------------------------------------------------
// llm_orb.gdshader
// The "orb form": the character compressed into a single context window.
//   layer 0 = TEXT SHELL - a globe whose latitude rows are lines of text,
//             alternating scroll direction (a spinning token sphere),
//             rim-lit and sliced by a scanning meridian.
//   layer 1 = CORE       - a white-hot, churning nucleus with an
//             attention-pulse heartbeat.
// `form` (0..1) assembles the orb row by row from the equator outward.
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform int layer = 0;
uniform float form : hint_range(0.0, 1.0) = 1.0;
uniform float charge : hint_range(0.0, 1.0) = 0.0;  // speed boost / dash flare
uniform float rows = 22.0;
uniform float cols = 46.0;
uniform float scroll = 4.0;
uniform float hue = 0.6;
uniform float intensity = 1.2;

varying vec3 obj_pos;

void vertex() {
	obj_pos = VERTEX;
	if (layer == 1) {
		// churning nucleus: wobble the core surface
		float n = vnoise3(VERTEX * 6.0 + vec3(0.0, TIME * 2.5, 0.0));
		VERTEX *= 1.0 + (n - 0.5) * 0.35 * (0.6 + charge);
	}
}

void fragment() {
	float fres = pow(1.0 - abs(dot(NORMAL, VIEW)), 2.2);
	float beat = pow(0.5 + 0.5 * sin(TIME * 7.0), 6.0);
	if (layer == 1) {
		float n = vnoise3(obj_pos * 9.0 - vec3(0.0, TIME * 3.0, 0.0));
		vec3 c = mix(vec3(0.3, 0.9, 1.0), vec3(1.0), 0.5 + 0.5 * n);
		float core = (1.0 - fres * 0.8) * (0.75 + beat * 0.5 + charge * 0.8);
		ALBEDO = c * core * intensity * form;
	} else {
		// --- text shell ---------------------------------------------------------
		vec2 uv = UV;
		float lat = abs(uv.y - 0.5) * 2.0;           // 0 equator .. 1 pole
		if (lat > form * 1.05) {
			discard;
		}
		vec2 p = vec2(uv.x * cols, uv.y * rows);
		// alternate rows spin in opposite directions
		float row = floor(p.y);
		float dir = mod(row, 2.0) < 0.5 ? 1.0 : -1.0;
		p.x += TIME * scroll * dir * (1.0 + charge * 3.0);
		ivec3 cell;
		vec3 t = text_plane(p, TIME, 6.0 + charge * 20.0, 90, 0.0, cell);
		float rnd = hash_i3(cell);
		// glyphs squash toward the poles, fade them there
		float pole_fade = 1.0 - smoothstep(0.7, 0.95, lat);
		// scanning meridian
		float mer = fract(uv.x - TIME * 0.35);
		float meridian = exp(-pow(min(mer, 1.0 - mer) / 0.02, 2.0));
		// assembling edge glows
		float assemble = exp(-pow((lat - form) / 0.06, 2.0)) * (1.0 - step(0.999, form));

		vec3 col = llm_palette(hue + 0.25 * rnd + fres * 0.2);
		col = mix(col, ATTENTION_AMBER * 1.3, step(0.97, rnd) * 0.9);
		vec3 e = col * (t.x * 1.6 + t.y * 0.3) * pole_fade * (FRONT_FACING ? 1.0 : 0.35);
		e += llm_palette(0.7) * fres * (0.5 + beat * 0.4);
		e += vec3(0.7, 1.0, 1.0) * meridian * 0.8 * pole_fade;
		e += vec3(0.8, 1.0, 1.0) * assemble * 3.0;
		ALBEDO = e * intensity * (1.0 + charge);
	}
}
