// ---------------------------------------------------------------------------
// llm_character.gdshader
// Main surface shader for the LLM character.
//
//  * DISINTEGRATION  - the body is "detokenized": a sweep/radial field eats
//    the mesh voxel by voxel. Right before a voxel vanishes it is rewritten
//    as glowing glyphs that rapidly re-sample (scramble) like an LLM picking
//    tokens, and the very front of the edge burns white-hot.
//  * DATA SKIN       - faint lines of streaming text across the surface,
//    revealed by fresnel and by a periodic horizontal "inference scan".
//  * INTERIOR        - back faces render as a dense, dark terminal full of
//    text, so the holes in the body show it is made of language inside.
//  * GLITCH          - vertical slices of the body are displaced and
//    tinted during dashes (frame-tearing / packet-loss look).
//
// Rest-pose positions are baked into CUSTOM0 by llm_character_vfx.gd, so
// glyphs and dissolve cells stick to the skin while the skeleton animates.
// ---------------------------------------------------------------------------
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque, diffuse_burley, specular_schlick_ggx;

#include "res://vfx/shaders/glyph_common.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, hint_default_white;
uniform float roughness = 0.6;

group_uniforms dissolve;
uniform float dissolve_progress : hint_range(0.0, 1.0) = 0.0;
uniform vec3 dissolve_origin = vec3(0.0, 0.0, 0.0);    // rest/model space
uniform vec3 dissolve_axis = vec3(0.0, 1.0, 0.0);      // linear sweep direction
uniform float dissolve_extent = 1.3;                   // length of the sweep
uniform float dissolve_radial : hint_range(0.0, 1.0) = 0.0; // 0 = linear sweep, 1 = collapse toward origin
uniform float dissolve_noise : hint_range(0.0, 1.0) = 0.35;
uniform float dissolve_band = 0.16;                    // width of the glyph band (in field units)
uniform float voxel_size = 0.035;                      // dissolve cell size (m)
uniform float edge_heat = 3.5;                         // emission of the burning edge

group_uniforms text;
uniform float glyph_size = 0.03;                      // text cell height (m)
uniform float scramble_rate = 9.0;                     // token resamples / s in the band
uniform float idle_scramble_rate = 1.5;
uniform float text_scroll = 2.5;                       // cells / s
uniform float data_skin : hint_range(0.0, 1.0) = 0.25; // always-on hologram text
uniform float fresnel_power = 2.5;
uniform vec4 rim_color : source_color = vec4(0.0, 0.85, 1.0, 1.0);
uniform float scan_speed = 0.55;                       // inference scan passes / s
uniform float scan_strength = 1.0;
uniform float interior_strength = 1.6;

group_uniforms glitch;
uniform float glitch : hint_range(0.0, 1.0) = 0.0;
uniform vec3 glitch_dir = vec3(1.0, 0.0, 0.0);          // model space, usually -dash dir
uniform float overdrive : hint_range(0.0, 1.0) = 0.0;   // boosts all text emission (dash / orb charge)

varying vec3 rest_pos;
varying vec3 rest_nrm;
varying float glitch_slice;

// The dissolve field. Mirrored in glyph_hash.gd::dissolve_field().
float dissolve_field(vec3 p) {
	vec3 d = p - dissolve_origin;
	float lin = dot(d, dissolve_axis) / dissolve_extent;
	float rad = 1.0 - length(d) / dissolve_extent;
	float h = mix(lin, rad, dissolve_radial);
	float n = hash_i3(ivec3(floor(p / voxel_size)));
	return clamp(mix(h, n, dissolve_noise), 0.0, 1.0);
}

void vertex() {
	rest_pos = CUSTOM0.xyz;
	rest_nrm = NORMAL;
	glitch_slice = 0.0;
	if (glitch > 0.0) {
		// tear the body into horizontal slices that jump along glitch_dir
		float slice = floor(rest_pos.y / 0.045);
		float tick = floor(TIME * 24.0);
		float r = hash_i3(ivec3(int(slice), int(tick), 3));
		float on = step(1.0 - glitch * 0.4, r);
		float amount = (hash_i3(ivec3(int(slice), int(tick), 9)) - 0.25) * 0.09 * glitch;
		VERTEX += normalize(glitch_dir) * amount * on;
		glitch_slice = on;
	}
}

// triplanar text: three projected text planes blended by the rest normal
vec3 triplanar_text(vec3 p, vec3 n, float rate, out float has_glyph) {
	vec3 w = pow(abs(n), vec3(6.0));
	w /= (w.x + w.y + w.z + 1e-5);
	vec3 s = p / glyph_size;
	ivec3 cx; ivec3 cy; ivec3 cz;
	// horizontal lines of text: rows are along world-ish Y on side planes
	vec3 tx = text_plane(vec2(s.z * 0.8, s.y), TIME, rate, 0, text_scroll, cx);
	vec3 ty = text_plane(vec2(s.x * 0.8, s.z), TIME, rate, 1, text_scroll, cy);
	vec3 tz = text_plane(vec2(s.x * 0.8, s.y), TIME, rate, 2, text_scroll, cz);
	has_glyph = tx.z * w.x + ty.z * w.y + tz.z * w.z;
	return vec3(
		tx.x * w.x + ty.x * w.y + tz.x * w.z,
		tx.y * w.x + ty.y * w.y + tz.y * w.z,
		hash_i3(cx) * w.x + hash_i3(cy) * w.y + hash_i3(cz) * w.z);
}

void fragment() {
	float field = dissolve_field(rest_pos);
	float p = dissolve_progress;
	float threshold = p * (1.0 + dissolve_band) - dissolve_band;
	float edge = field - threshold;            // <0 gone, 0..band glyph band, >band intact
	if (edge < 0.0) {
		discard;
	}
	float band_t = clamp(edge / dissolve_band, 0.0, 1.0); // 0 at burning front, 1 at intact skin
	float in_band = 1.0 - smoothstep(0.75, 1.0, band_t);

	// text gets frantic inside the band, calm on the intact skin
	float rate = mix(scramble_rate, idle_scramble_rate, band_t);
	float has_glyph;
	vec3 txt = triplanar_text(rest_pos, rest_nrm, rate, has_glyph);
	float glyph = txt.x;
	float halo = txt.y;
	float cell_rand = txt.z;

	// letter cutout: approaching the front only glyph strokes survive, so the
	// body literally comes apart as characters (word gaps open first)
	float cut = smoothstep(0.6, 0.12, band_t);
	if (cut > 0.02 && glyph < cut * 0.55) {
		discard;
	}

	vec3 base = texture(albedo_tex, UV).rgb;
	vec3 V = VIEW;
	vec3 N = FRONT_FACING ? NORMAL : -NORMAL;
	float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), fresnel_power);

	// the inference scan: a thin bright band sweeping up the body
	float scan_y = fract(TIME * scan_speed) * 1.6 - 0.15;
	float scan = exp(-pow((rest_pos.y - scan_y) / 0.035, 2.0)) * scan_strength;
	float scan_trail = smoothstep(scan_y - 0.35, scan_y, rest_pos.y) * step(rest_pos.y, scan_y) * 0.35 * scan_strength;

	vec3 emis = vec3(0.0);

	if (!FRONT_FACING) {
		// --- interior: the body is a terminal full of text -----------------
		float g = glyph;
		vec3 col = llm_palette(0.45 + 0.4 * cell_rand) * (0.25 + 1.2 * g) + vec3(0.0, 0.05, 0.12) * halo;
		ALBEDO = vec3(0.0);
		ROUGHNESS = 1.0;
		SPECULAR = 0.0;
		EMISSION = col * interior_strength * (1.0 + overdrive);
	} else {

		// --- data skin: hologram text over the albedo -----------------------------
		float skin_mask = clamp(data_skin * (0.35 + fres * 1.6) + scan * 1.4 + scan_trail + overdrive * 0.45, 0.0, 1.5);
		vec3 skin_col = mix(rim_color.rgb, llm_palette(0.55 + 0.45 * cell_rand), 0.5);
		emis += skin_col * glyph * skin_mask * 1.4;
		emis += rim_color.rgb * fres * (0.35 + overdrive * 0.7) * (0.6 + 0.4 * data_skin);
		emis += rim_color.rgb * scan * 0.6;

		// --- dissolve band: skin rewritten as tokens --------------------------------
		vec3 albedo = base;
		if (in_band > 0.0) {
			// darken skin toward "unrendered" terminal black as it nears the front
			albedo = mix(base, base * 0.08, in_band);
			float heat = 1.0 - band_t;                           // 1 at front
			vec3 tok_col = llm_palette(0.35 + heat * 0.65);
			// rare amber "attention" tokens
			tok_col = mix(tok_col, ATTENTION_AMBER * 1.4, step(0.965, cell_rand) * 0.85);
			float g = max(glyph, has_glyph * 0.06);
			emis += tok_col * (g * 3.0 + halo * 0.5) * in_band * (1.0 + overdrive * 0.5);
			// white-hot burning front: the last glyphs flare before they detach
			float front = 1.0 - smoothstep(0.0, 0.12, band_t);
			emis += vec3(0.75, 0.95, 1.0) * front * edge_heat * (0.25 + glyph);
		}

		// glitch slices get a hard colour shift
		if (glitch_slice > 0.5) {
			emis += llm_palette(0.3 + 0.7 * hash_f1(floor(TIME * 24.0) + rest_pos.y)) * glyph * 2.5 * glitch;
			emis += llm_palette(0.6) * 0.25 * glitch;
			albedo *= 0.6;
		}

		ALBEDO = albedo;
		ROUGHNESS = roughness;
		EMISSION = emis;
	}
}
