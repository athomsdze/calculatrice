"""Génère assets/icon.ico et assets/icon.png (nécessite Pillow).

    python tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZE = 512
TOP, BOTTOM = (124, 120, 255), (79, 70, 229)


def draw_icon(size: int = SIZE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # fond dégradé vertical dans un carré arrondi
    gradient = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,)
        gd.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.23, fill=255)
    img.paste(gradient, (0, 0), mask)

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    white = (255, 255, 255, 255)
    soft = (255, 255, 255, 120)
    u = size / 16
    # écran
    d.rounded_rectangle([3 * u, 2.8 * u, 13 * u, 6.2 * u], radius=u * 0.9, fill=(255, 255, 255, 60))
    d.rounded_rectangle([8.2 * u, 4.1 * u, 11.8 * u, 4.9 * u], radius=u * 0.4, fill=white)
    # touches 3 x 2
    keys = [(3, 7.6), (6.6, 7.6), (10.2, 7.6), (3, 10.4), (6.6, 10.4)]
    for x, y in keys:
        d.rounded_rectangle([x * u, y * u, (x + 2.8) * u, (y + 2.2) * u], radius=u * 0.7, fill=soft)
    # touche « = » mise en avant
    d.rounded_rectangle([10.2 * u, 10.4 * u, 13 * u, 12.6 * u], radius=u * 0.7, fill=white)
    for dy in (11.05, 11.65):
        d.rounded_rectangle([10.9 * u, dy * u, 12.3 * u, (dy + 0.32) * u], radius=u * 0.16,
                            fill=BOTTOM + (255,))
    return Image.alpha_composite(img, overlay)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    icon = draw_icon()
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                          (128, 128), (256, 256)])
    print("Icônes générées dans", ASSETS)


if __name__ == "__main__":
    main()
