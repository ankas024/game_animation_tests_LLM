// ---------------------------------------------------------------------------
// glyph_common.gdshaderinc
// Shared helpers for the "LLM token" VFX family.
//   * deterministic integer hashing (mirrored 1:1 in vfx/scripts/glyph_hash.gd
//     so the CPU can predict exactly which cells are dissolving and emit
//     particles there)
//   * glyph atlas sampling with seam-free mip selection
//   * token scrambling ("the model is still sampling this token")
//   * the shared colour language of the effect
// ---------------------------------------------------------------------------

uniform sampler2D glyph_atlas : hint_default_black, filter_linear_mipmap, repeat_disable;

const float GLYPH_GRID = 16.0;
const float GLYPH_COUNT = 239.0; // unique glyphs in the atlas

// --- hashing ---------------------------------------------------------------
uint pcg_hash(uint v) {
	uint state = v * 747796405u + 2891336453u;
	uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
	return (word >> 22u) ^ word;
}
float hash_i3(ivec3 c) {
	uint h = pcg_hash(uint(c.x) + pcg_hash(uint(c.y) + pcg_hash(uint(c.z))));
	return float(h) * (1.0 / 4294967295.0);
}
float hash_i2(ivec2 c) { return hash_i3(ivec3(c, 7919)); }
float hash_f1(float x) { return fract(sin(x * 127.1) * 43758.5453); }
vec2 hash_f2(vec2 p) {
	p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
	return fract(sin(p) * 43758.5453);
}

// smooth value noise (purely visual, never mirrored on CPU)
float vnoise3(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	ivec3 c = ivec3(i);
	float a = mix(hash_i3(c), hash_i3(c + ivec3(1, 0, 0)), f.x);
	float b = mix(hash_i3(c + ivec3(0, 1, 0)), hash_i3(c + ivec3(1, 1, 0)), f.x);
	float d = mix(hash_i3(c + ivec3(0, 0, 1)), hash_i3(c + ivec3(1, 0, 1)), f.x);
	float e = mix(hash_i3(c + ivec3(0, 1, 1)), hash_i3(c + ivec3(1, 1, 1)), f.x);
	return mix(mix(a, b, f.y), mix(d, e, f.y), f.z);
}

// --- glyphs ----------------------------------------------------------------
// Picks a glyph for a cell. `rate` = how many times per second the token is
// resampled. Each cell gets its own phase so the grid never flips in unison.
float token_index(ivec3 cell, float t, float rate) {
	float phase = hash_i3(cell + ivec3(17, 3, 101));
	float epoch = floor(t * rate + phase * 13.0);
	return floor(hash_i3(cell + ivec3(int(epoch) * 31, int(epoch) * 7, 0)) * GLYPH_COUNT);
}

// Samples glyph `idx` at in-cell coordinate `local` (0..1). `cont` is the
// continuous (un-fract'ed) coordinate used only for derivatives so mip
// selection does not explode at cell borders.
// returns x = crisp coverage, y = soft halo, z = in-cell vertical gradient
vec3 glyph_sample(float idx, vec2 local, vec2 cont) {
	vec2 g = vec2(mod(idx, GLYPH_GRID), floor(idx / GLYPH_GRID));
	vec2 l = clamp(local, 0.0, 1.0);
	l.y = 1.0 - l.y;
	vec2 uv = (g + 0.08 + l * 0.84) / GLYPH_GRID;
	vec2 dx = dFdx(cont) * (0.84 / GLYPH_GRID);
	vec2 dy = dFdy(cont) * (0.84 / GLYPH_GRID);
	return textureGrad(glyph_atlas, uv, dx, dy).rgb;
}

// Lays out text "lines" on a 2D plane: rows of glyphs with word gaps.
// p is in cell units. Returns x = coverage, y = halo, z = 1 when the cell
// holds a glyph (not a space). `cell_out` returns the integer cell id.
vec3 text_plane(vec2 p, float t, float scramble_rate, int plane_id, float scroll, out ivec3 cell_out) {
	float row = floor(p.y);
	// each row scrolls at its own speed / direction like a live token stream
	float row_speed = (hash_f1(row + float(plane_id) * 31.0) - 0.5) * 2.0 * scroll;
	vec2 q = vec2(p.x + t * row_speed, p.y);
	vec2 cell = floor(q);
	vec2 local = fract(q);
	ivec3 c = ivec3(ivec2(cell), plane_id);
	cell_out = c;
	// word gaps: roughly one space every ~5 glyphs, plus sparse empty rows
	float word = hash_i3(c + ivec3(0, 0, 977));
	float blank_row = step(0.82, hash_i3(ivec3(0, int(row), plane_id + 55)));
	float has = step(0.2, word) * (1.0 - blank_row);
	// squeeze glyphs horizontally a bit: monospace terminal look
	local.x = (local.x - 0.5) * 1.15 + 0.5;
	float idx = token_index(c, t, scramble_rate);
	vec3 g = glyph_sample(idx, local, q);
	return vec3(g.x * has, g.y * has, has);
}

// --- colour ----------------------------------------------------------------
// 0 -> deep indigo, 0.35 -> violet, 0.6 -> electric cyan, 1 -> white-hot
vec3 llm_palette(float x) {
	x = clamp(x, 0.0, 1.0);
	vec3 c0 = vec3(0.05, 0.02, 0.22);
	vec3 c1 = vec3(0.45, 0.10, 0.95);
	vec3 c2 = vec3(0.00, 0.85, 1.00);
	vec3 c3 = vec3(0.92, 1.00, 1.00);
	vec3 c = mix(c0, c1, smoothstep(0.0, 0.35, x));
	c = mix(c, c2, smoothstep(0.35, 0.65, x));
	c = mix(c, c3, smoothstep(0.7, 1.0, x));
	return c;
}
// rare "highlighted token" accent (attention hot-spot)
const vec3 ATTENTION_AMBER = vec3(1.0, 0.55, 0.08);
