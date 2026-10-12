#!/usr/bin/env bash
# Renders the VFX showcase with Godot's Movie Maker and encodes MP4 + GIF + stills.
#   GODOT=/path/to/Godot_v4.5.1-stable_linux.x86_64 vfx/tools/render_showcase.sh [WxH]
# Headless machines: runs under xvfb-run with the OpenGL (Compatibility) renderer.
set -euo pipefail
cd "$(dirname "$0")/../.."
GODOT="${GODOT:-godot}"
RES="${1:-1280x720}"
OUT="docs/vfx"
TMP="renders_tmp/showcase"
rm -rf "$TMP" && mkdir -p "$TMP" "$OUT"

timeout 300 "$GODOT" --headless --import >/dev/null 2>&1 || true
RUN=("$GODOT" --rendering-driver opengl3 --resolution "$RES" --write-movie "$TMP/f.png" --fixed-fps 30 -- --showcase-once)
if [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null; then
	xvfb-run -a -s "-screen 0 1920x1080x24" "${RUN[@]}"
else
	"${RUN[@]}"
fi

ffmpeg -y -loglevel error -framerate 30 -i "$TMP/f%08d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart "$OUT/llm_vfx_showcase.mp4"
ffmpeg -y -loglevel error -framerate 30 -i "$TMP/f%08d.png" \
	-vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
	"$OUT/llm_vfx_showcase.gif"
echo "wrote $OUT/llm_vfx_showcase.mp4 and .gif"
