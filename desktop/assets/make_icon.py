"""Genera l'icona dell'applicazione.

    python make_icon.py

Icona provvisoria, pensata per essere sostituita da quella definitiva del
cliente: quadrato arrotondato indaco con la "S" e un segno di spunta.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
BG = (79, 70, 229)
FG = (255, 255, 255)
OUT = Path(__file__).with_name("icon.ico")


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.22), fill=BG)

letter = font(int(SIZE * 0.58))
draw.text((SIZE / 2, SIZE * 0.44), "S", font=letter, fill=FG, anchor="mm")

# Segno di spunta in basso a destra: "fatto", il senso di uno scadenzario.
w = int(SIZE * 0.055)
draw.line(
    [(SIZE * 0.60, SIZE * 0.74), (SIZE * 0.68, SIZE * 0.82), (SIZE * 0.83, SIZE * 0.62)],
    fill=FG,
    width=w,
    joint="curve",
)

image.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"icona creata: {OUT}")
