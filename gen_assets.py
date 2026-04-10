"""
Generate brand assets (favicon PNG + Open Graph image) using Pillow.

Outputs:
  output/favicon-192.png        — 192x192 PNG favicon (for browsers that prefer PNG)
  output/favicon-512.png        — 512x512 PNG favicon (PWA, Android)
  output/apple-touch-icon.png   — 180x180 PNG (iOS home screen)
  output/og-image.png           — 1200x630 PNG (Kakao/Slack/Facebook link preview)

Design follows favicon.svg: orange eye outline, blue iris, orange rays.
OG image adds the "Market Summary" title on a light background.

Run: python3.12 gen_assets.py
"""

import os
from PIL import Image, ImageDraw, ImageFont

# ── Mirae Asset brand palette ───────────────────────────────────────────
ORANGE = "#F58220"
BLUE = "#043B72"
ORANGE_DARK = "#CB6015"
NEAR_BLACK = "#1a1d2e"
BG_LIGHT = "#f4f5f9"
MUTED = "#7c8298"
WHITE = "#ffffff"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Spoqa Han Sans ttf from the Mirae skill (if available), else fall back.
SPOQA_BOLD = os.path.expanduser(
    "~/.claude/skills/mirae-asset-design/assets/fonts/Spoqa Han Sans Bold.ttf"
)
SPOQA_REGULAR = os.path.expanduser(
    "~/.claude/skills/mirae-asset-design/assets/fonts/Spoqa Han Sans Regular.ttf"
)
APPLE_SD = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def _load_font(size: int, bold: bool = False):
    """Load Spoqa Han Sans if present, else macOS Apple SD Gothic Neo, else default."""
    candidates = []
    if bold:
        candidates = [SPOQA_BOLD, APPLE_SD]
    else:
        candidates = [SPOQA_REGULAR, APPLE_SD]
    for path in candidates:
        if os.path.exists(path):
            try:
                # AppleSDGothicNeo is a .ttc — index 2 is bold-ish
                if path.endswith(".ttc"):
                    return ImageFont.truetype(path, size, index=2 if bold else 0)
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_eye(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float):
    """Draw the 'third eye' symbol matching favicon.svg, scaled from 64x64 base."""
    # favicon.svg viewBox is 64x64. Scale everything by (size / 64).
    s = scale
    stroke_main = max(2, int(3 * s))
    stroke_thin = max(2, int(2 * s))
    stroke_ray = max(2, int(1.5 * s))

    # Outer eye ellipse: cx=32, cy=32, rx=28, ry=16
    rx, ry = int(28 * s), int(16 * s)
    draw.ellipse(
        [cx - rx, cy - ry, cx + rx, cy + ry],
        outline=ORANGE,
        width=stroke_main,
    )

    # Upper lid: quadratic Bezier approximated as an arc
    # M4 32 Q32 10 60 32 — peaks at y=10 (22 above center)
    # Using draw.arc for approximation: the ellipse that fits the curve
    upper_rx = int(28 * s)
    upper_ry = int(22 * s)
    draw.arc(
        [cx - upper_rx, cy - upper_ry, cx + upper_rx, cy + upper_ry],
        start=180,
        end=360,
        fill=ORANGE,
        width=stroke_main,
    )
    # Lower lid: Q32 54 — dips to y=54 (22 below center)
    draw.arc(
        [cx - upper_rx, cy - upper_ry, cx + upper_rx, cy + upper_ry],
        start=0,
        end=180,
        fill=ORANGE,
        width=stroke_main,
    )

    # Iris: r=11
    ir = int(11 * s)
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=BLUE)

    # Pupil: r=5.5
    pr = max(2, int(5.5 * s))
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=NEAR_BLACK)

    # Highlight: cx+3, cy-3, r=2.5
    hr = max(1, int(2.5 * s))
    hx, hy = cx + int(3 * s), cy - int(3 * s)
    draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=WHITE)

    # Third-eye rays (top three lines)
    # Top vertical: (32,4)→(32,12)
    draw.line(
        [(cx, cy - int(28 * s)), (cx, cy - int(20 * s))],
        fill=ORANGE_DARK,
        width=stroke_thin,
    )
    # Top-left diagonal: (14,10)→(19,17)
    draw.line(
        [
            (cx - int(18 * s), cy - int(22 * s)),
            (cx - int(13 * s), cy - int(15 * s)),
        ],
        fill=ORANGE_DARK,
        width=stroke_ray,
    )
    # Top-right diagonal: (50,10)→(45,17)
    draw.line(
        [
            (cx + int(18 * s), cy - int(22 * s)),
            (cx + int(13 * s), cy - int(15 * s)),
        ],
        fill=ORANGE_DARK,
        width=stroke_ray,
    )


def make_favicon(size: int, out_path: str, bg: str | None = None):
    """Generate a square favicon PNG at the given pixel size."""
    if bg is None:
        img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    else:
        img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)
    scale = size / 64.0
    draw_eye(draw, size // 2, size // 2, scale)
    img.save(out_path, "PNG")
    print(f"  wrote {out_path} ({size}x{size})")


def make_og_image(out_path: str):
    """Generate a 1200x630 Open Graph link preview image."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG_LIGHT)
    draw = ImageDraw.Draw(img)

    # Top orange accent bar (12px)
    draw.rectangle([0, 0, W, 12], fill=ORANGE)

    # Eye symbol on the left
    eye_cx, eye_cy = 240, H // 2 + 10
    draw_eye(draw, eye_cx, eye_cy, scale=5.0)  # 5.0 × 64 = 320px wide

    # Title + subtitle on the right
    title_x = 470
    title_y = 205

    font_title = _load_font(84, bold=True)
    font_sub = _load_font(36, bold=False)

    # Main title
    draw.text((title_x, title_y), "Market Summary", font=font_title, fill=NEAR_BLACK)

    # Subtitle
    draw.text(
        (title_x, title_y + 120),
        "매일 자동 생성되는 글로벌 시장 요약 보고서",
        font=font_sub,
        fill=MUTED,
    )

    # Divider (Mirae blue)
    draw.rectangle([title_x, title_y + 185, title_x + 80, title_y + 189], fill=BLUE)

    # Footer caption
    font_small = _load_font(24, bold=False)
    draw.text(
        (title_x, title_y + 210),
        "Data Dashboard · Market Story",
        font=font_small,
        fill=MUTED,
    )

    img.save(out_path, "PNG", optimize=True)
    print(f"  wrote {out_path} ({W}x{H})")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Generating brand assets…")
    make_favicon(192, os.path.join(OUT_DIR, "favicon-192.png"))
    make_favicon(512, os.path.join(OUT_DIR, "favicon-512.png"))
    make_favicon(180, os.path.join(OUT_DIR, "apple-touch-icon.png"), bg=BG_LIGHT)
    make_og_image(os.path.join(OUT_DIR, "og-image.png"))
    print("Done.")


if __name__ == "__main__":
    main()