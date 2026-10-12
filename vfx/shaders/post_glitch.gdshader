// ---------------------------------------------------------------------------
// post_glitch.gdshader
// Applied to the SubViewportContainer that shows the 3D scene.
// Impact frames for dashes / transformations: chromatic split along the
// motion direction, horizontal block tearing, scanlines and a vignette.
// ---------------------------------------------------------------------------
shader_type canvas_item;

uniform float impact : hint_range(0.0, 1.0) = 0.0;
uniform vec2 push_dir = vec2(1.0, 0.0);
uniform float vignette = 0.45;
uniform float grain = 0.025;

float h1(float x) { return fract(sin(x * 91.3458) * 47453.5453); }

void fragment() {
	vec2 uv = UV;
	float t = floor(TIME * 30.0);
	float band = floor(uv.y * 54.0);
	float tear = step(1.0 - impact * 0.18, h1(band + t * 1.7));
	uv.x += (h1(band * 3.1 + t) - 0.5) * 0.035 * impact * tear;
	vec2 off = normalize(push_dir + vec2(1e-4)) * (0.0015 + 0.008 * impact);
	vec3 col;
	col.r = texture(TEXTURE, uv + off).r;
	col.g = texture(TEXTURE, uv).g;
	col.b = texture(TEXTURE, uv - off).b;
	col += vec3(0.0, 0.08, 0.14) * tear * impact;
	col *= 1.0 - (0.06 + impact * 0.14) * (0.5 + 0.5 * sin(FRAGCOORD.y * 2.1));
	vec2 q = UV - 0.5;
	col *= 1.0 - vignette * smoothstep(0.3, 0.9, length(q * vec2(1.25, 1.0)));
	col += (h1(dot(FRAGCOORD.xy, vec2(1.0, 57.0)) + TIME) - 0.5) * grain;
	COLOR = vec4(col, 1.0);
}
