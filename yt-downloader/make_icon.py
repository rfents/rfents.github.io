#!/usr/bin/env python3
"""Draw the "FD" app icon into assets/ (PNG, Windows .ico, macOS .icns).

The generated files are committed, so this only needs re-running to change
the design:  python -m pip install pillow && python make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets"
S = 1024  # draw large, then downscale for crisp small sizes

NAVY_TOP, NAVY_BOTTOM = (14, 34, 78), (4, 10, 24)
CYAN, BLUE, WHITE = (0, 217, 255), (47, 107, 255), (228, 239, 255)

FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf",
]


def load_font(size):
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise SystemExit("No bold TrueType font found; edit FONT_CANDIDATES.")


def draw_icon() -> Image.Image:
    radius, margin = int(S * 0.2), int(S * 0.04)
    box = (margin, margin, S - margin, S - margin)

    # vertical navy gradient clipped to a rounded square
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOTTOM)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, mask=mask)

    # faint grid inside the tile
    grid = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(grid)
    for p in range(margin, S - margin, S // 16):
        gdr.line([(p, margin), (p, S - margin)], fill=(40, 80, 160, 40), width=3)
        gdr.line([(margin, p), (S - margin, p)], fill=(40, 80, 160, 40), width=3)
    img.alpha_composite(Image.composite(grid, Image.new("RGBA", (S, S)), mask))

    # neon border with glow
    border = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(box, radius, outline=CYAN + (255,), width=int(S * 0.025))
    img.alpha_composite(border.filter(ImageFilter.GaussianBlur(S * 0.02)))
    img.alpha_composite(border)

    # "FD" lettering: F in cyan with glow, D in white
    font = load_font(int(S * 0.5))
    d = ImageDraw.Draw(img)
    f_w = d.textlength("F", font=font)
    total = f_w + d.textlength("D", font=font) - S * 0.02
    x0 = (S - total) / 2
    top, bottom = d.textbbox((0, 0), "FD", font=font)[1::2]
    y0 = (S - (bottom - top)) / 2 - top - S * 0.03

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((x0, y0), "F", font=font, fill=CYAN + (255,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * 0.03)))
    d.text((x0, y0), "F", font=font, fill=CYAN)
    d.text((x0 + f_w - S * 0.02, y0), "D", font=font, fill=WHITE)

    # accent bar under the letters
    bar_y = y0 + bottom + S * 0.06
    d.rounded_rectangle((S * 0.3, bar_y, S * 0.7, bar_y + S * 0.035), S * 0.02, fill=BLUE)
    return img


def main():
    OUT.mkdir(exist_ok=True)
    img = draw_icon()
    img.resize((256, 256), Image.LANCZOS).save(OUT / "fenix.png")
    img.save(OUT / "fenix.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(OUT / "fenix.icns")
    print("Wrote", ", ".join(p.name for p in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
