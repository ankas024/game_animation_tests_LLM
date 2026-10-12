// ---------------------------------------------------------------------------
// token_ribbon.gdshader
// Ribbons of streaming text: dash limb trails, the body wake sheet, the
// orb's trail and the orb's orbiting rings.
//   UV.x  = distance along the ribbon in metres (anchored to where the
//           point was emitted, so text stays put in the world)
//   UV.y  = 0..1 across the ribbon
//   COLOR.a = remaining life of that ribbon point
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform float rows = 1.0;                 // lines of text across the ribbon
uniform float glyph_aspect = 0.75;        // glyph width / height
uniform float scroll_speed = 1.5;         // text flow along the ribbon (cells/s)
uniform float scramble_rate = 10.0;
uniform float hue = 0.62;
uniform float hue_spread = 0.25;
uniform float core_width = 0.12;          // bright spine down the middle (0 = none)
uniform float edge_softness = 0.25;
uniform float intensity = 2.0;
uniform float ribbon_width = 0.1;         // world width, keeps glyphs square-ish
uniform float id_offset = 0.0;
uniform float glyph_fill : hint_range(0.0, 1.0) = 1.0;

void fragment() {
	float life = COLOR.a;
	float cell_h = 1.0 / rows;
	float glyph_w = ribbon_width * cell_h * glyph_aspect;
	vec2 p = vec2(UV.x / glyph_w, UV.y * rows);
	// keep text upright and readable whichever way the ribbon travels on screen
	if (UV2.x > 0.5) {
		p = vec2(-p.x, rows - p.y);
	}
	if (!FRONT_FACING) {
		p.x = -p.x;
	}
	ivec3 cell;
	vec3 t = text_plane(p, TIME, scramble_rate, int(id_offset) + 40, scroll_speed, cell);
	float rnd = hash_i3(cell);
	t *= step(1.0 - glyph_fill, rnd);

	float across = abs(UV.y - 0.5) * 2.0;
	float edge = 1.0 - smoothstep(1.0 - edge_softness, 1.0, across);
	float core = core_width > 0.0 ? exp(-pow(across / core_width, 2.0)) : 0.0;

	float l2 = life * life;
	vec3 col = llm_palette(hue + hue_spread * (life - 0.5) + 0.15 * rnd);
	col = mix(col, ATTENTION_AMBER * 1.3, step(0.975, rnd) * 0.8);
	vec3 e = col * (t.x * 1.5 + t.y * 0.3) * edge * l2;
	e += mix(col, vec3(0.9, 1.0, 1.0), 0.5) * core * life * l2 * 1.2;
	// shimmer: sparse bright flickers along the trail
	float sp = step(0.985, hash_f2(floor(vec2(UV.x * 60.0, UV.y * rows * 3.0 + TIME * 20.0))).x);
	e += vec3(0.8, 1.0, 1.0) * sp * edge * life;
	ALBEDO = e * intensity * COLOR.rgb;
}
