#!/usr/bin/env bash
# Generate eglk-harness demo GIF (no live LLM).
set -euo pipefail
HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
SITE="${EGLK_SITE_DIR:-$HARNESS/docs/site}"
ASSETS="$SITE/assets"
mkdir -p "$ASSETS"
FRAMES="$ASSETS/_frames"
rm -rf "$FRAMES"
mkdir -p "$FRAMES"

python3 - <<PY
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

frames_dir = Path("$FRAMES")
slides = [
    ("eglk-harness", "Evidence-Gated Loop Kernel"),
    ("Maker → Claim", "Checker → Evidence"),
    ("Gate (mechanical)", "admit / repair / abort"),
    ("Σ + dynamic tree", "zero HITL"),
    ("WA-Hard primary", "scores never Gate"),
    ("init · doctor · run", ":28000 live"),
]
W, H = 960, 540
for i, (title, sub) in enumerate(slides):
    img = Image.new("RGB", (W, H), (18, 22, 32))
    draw = ImageDraw.Draw(img)
    try:
        font_l = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        font_l = ImageFont.load_default()
        font_s = ImageFont.load_default()
    draw.text((48, 180), title, fill=(120, 200, 255), font=font_l)
    draw.text((48, 260), sub, fill=(220, 225, 235), font=font_s)
    draw.rectangle([40, 40, W - 40, H - 40], outline=(60, 80, 120), width=2)
    img.save(frames_dir / f"frame_{i:02d}.png")
print(f"wrote {len(slides)} frames")
PY

GIF="$ASSETS/eglk-harness-demo.gif"
ffmpeg -y -loglevel error -framerate 1 -i "$FRAMES/frame_%02d.png" \
  -vf "fps=2,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  -loop 0 "$GIF"
echo "wrote $GIF"
ls -la "$GIF"
