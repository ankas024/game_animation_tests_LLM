#!/usr/bin/env bash
# Assemble preview media from rendered PNG frames (render_preview.py output).
#   tools/blender/make_media.sh <frames_dir> [out_dir]
set -euo pipefail
FR="$1"
OUT="${2:-$(cd "$(dirname "$0")/../.." && pwd)/docs/media}"
mkdir -p "$OUT"

# 60 fps master
ffmpeg -y -loglevel error -framerate 60 -i "$FR/f_%04d.png" \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart \
  "$OUT/sword_combo_preview.mp4"

# lightweight GIF for READMEs (24 fps, 480 wide)
ffmpeg -y -loglevel error -i "$OUT/sword_combo_preview.mp4" \
  -vf "fps=24,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  "$OUT/sword_combo_preview.gif"

# key-pose sheet
KEYS="44 52 60 96 116 140 179 192 205 246 258 312"
TMP=$(mktemp -d)
for f in $KEYS; do
  p=$(printf "%s/f_%04d.png" "$FR" "$f")
  convert "$p" -resize 480x270 -fill white -pointsize 16 -annotate +10+24 "f$f" "$TMP/k_$f.png"
done
montage $(for f in $KEYS; do echo "$TMP/k_$f.png"; done) -tile 4x -geometry +2+2 -background "#000" \
  "$OUT/sword_combo_keyposes.png"
rm -rf "$TMP"
ls -la "$OUT"
