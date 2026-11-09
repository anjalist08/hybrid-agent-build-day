"""Draws the Lens app icon (1024x1024) into the iOS asset catalog.

Concept: a glass camera lens (white rim, soft aperture, glassy interior) on a deep blue-to-indigo
gradient, with a four-point "AI" sparkle as the lens glint.

  cd backend && uv run python ../tools/icon/make_icon.py [output.png]
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 4096  # draw at 4x, downsample for clean edges
OUT = 1024
C = S / 2


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def diagonal_gradient(size, top_left, bottom_right):
    """Smooth diagonal gradient via a small image scaled up (fast, banding-free after resize)."""
    n = 256
    small = Image.new("RGB", (n, n))
    px = small.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            px[x, y] = lerp(top_left, bottom_right, t)
    return small.resize((size, size), Image.BICUBIC)


def radial(size, center, radius, inner, outer):
    """RGBA radial gradient (inner color at center -> outer color at radius)."""
    n = 256
    small = Image.new("RGBA", (n, n))
    px = small.load()
    cx, cy = center[0] * n / size, center[1] * n / size
    r = radius * n / size
    for y in range(n):
        for x in range(n):
            t = min(1.0, math.hypot(x - cx, y - cy) / r)
            px[x, y] = lerp(inner, outer, t)
    return small.resize((size, size), Image.BICUBIC)


def circle_mask(size, cx, cy, r, blur=0):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur else m


def sparkle(draw, cx, cy, r, fill, waist=0.26):
    """Four-point star with concave sides (the 'AI' glint)."""
    pts = []
    for i in range(16):
        ang = math.pi / 2 - i * math.pi / 8
        if i % 4 == 0:
            rad = r
        elif i % 2 == 0:
            rad = r * waist
        else:
            rad = r * waist * 1.25
        pts.append((cx + rad * math.cos(ang), cy - rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def main(out_path: Path):
    # Background: iOS blue -> indigo, with a soft light bloom top-left.
    img = diagonal_gradient(S, (18, 132, 255), (72, 52, 212)).convert("RGBA")
    bloom = radial(S, (S * 0.18, S * 0.12), S * 0.75, (255, 255, 255, 70), (255, 255, 255, 0))
    img = Image.alpha_composite(img, bloom)

    # Soft drop shadow under the lens.
    R = S * 0.33
    shadow = Image.new("RGBA", (S, S), (20, 10, 70, 0))
    shadow.putalpha(circle_mask(S, C + S * 0.012, C + S * 0.03, R * 1.02, blur=S * 0.03).point(lambda v: int(v * 0.45)))
    img = Image.alpha_composite(img, shadow)

    # White rim.
    rim = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    img = Image.composite(rim, img, circle_mask(S, C, C, R))

    # Glass interior: deep navy center fading to blue at the edge.
    glass_r = R * 0.84
    glass = radial(S, (C - glass_r * 0.15, C - glass_r * 0.2), glass_r * 1.25,
                   (40, 70, 190, 255), (10, 14, 48, 255))
    img = Image.composite(glass, img, circle_mask(S, C, C, glass_r))

    # Thin inner bezel ring.
    d = ImageDraw.Draw(img)
    br = glass_r * 0.985
    d.ellipse((C - br, C - br, C + br, C + br), outline=(160, 190, 255, 120), width=int(S * 0.006))

    # Lens elements: two faint concentric rings instead of literal aperture blades (cleaner when small).
    rings = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rgd = ImageDraw.Draw(rings)
    for frac, alpha in ((0.72, 55), (0.52, 80)):
        rr2 = glass_r * frac
        rgd.ellipse((C - rr2, C - rr2, C + rr2, C + rr2), outline=(140, 175, 255, alpha), width=int(S * 0.006))
    img = Image.alpha_composite(img, rings)
    pupil = radial(S, (C, C), glass_r * 0.34, (6, 8, 28, 255), (16, 24, 70, 255))
    img = Image.composite(pupil, img, circle_mask(S, C, C, glass_r * 0.30))

    # Glass reflections: a broad soft arc top-left, a small dot bottom-right.
    refl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(refl)
    rr = glass_r * 0.78
    rd.arc((C - rr, C - rr, C + rr, C + rr), start=200, end=255, fill=(255, 255, 255, 150), width=int(S * 0.028))
    rd.ellipse((C + glass_r * 0.38 - S * 0.018, C + glass_r * 0.42 - S * 0.018,
                C + glass_r * 0.38 + S * 0.018, C + glass_r * 0.42 + S * 0.018), fill=(255, 255, 255, 110))
    refl = refl.filter(ImageFilter.GaussianBlur(S * 0.004))
    glass_only = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glass_only.paste(refl, mask=ImageChops.multiply(refl.getchannel("A"), circle_mask(S, C, C, glass_r)))
    img = Image.alpha_composite(img, glass_only)

    # The AI sparkle: a glowing four-point star where light catches the lens, plus a small companion.
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    sx, sy = C + glass_r * 0.36, C - glass_r * 0.38
    sparkle(gd, sx, sy, S * 0.095, (255, 255, 255, 255))
    glow_blur = glow.filter(ImageFilter.GaussianBlur(S * 0.022))
    glow_blur = Image.alpha_composite(glow_blur, glow_blur)  # stronger halo
    img = Image.alpha_composite(img, glow_blur)
    img = Image.alpha_composite(img, glow)
    small = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sparkle(ImageDraw.Draw(small), sx - S * 0.075, sy - S * 0.07, S * 0.032, (255, 255, 255, 230))
    img = Image.alpha_composite(img, small)

    out = img.convert("RGB").resize((OUT, OUT), Image.LANCZOS)  # App Store icons must be opaque
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, "PNG")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[2] / "ios/Lens/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
