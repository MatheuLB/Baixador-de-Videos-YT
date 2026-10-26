"""Gera o ícone do app (assets/icon.png, icon.ico e icon.icns) com o Pillow.

Uso: python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZE = 1024
SCALE = 4  # desenha maior e reduz no fim, para bordas suaves


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_icon() -> Image.Image:
    big = SIZE * SCALE
    start, end = (124, 92, 255), (47, 123, 255)

    # Gradiente diagonal.
    gradient = Image.new("RGB", (big, big))
    small = Image.new("RGB", (256, 256))
    pixels = small.load()
    for y in range(256):
        for x in range(256):
            pixels[x, y] = lerp(start, end, (x + y) / 510)
    gradient = small.resize((big, big), Image.Resampling.BICUBIC)

    # Forma: quadrado bem arredondado, com margem como os ícones do macOS.
    margin = int(big * 0.09)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (margin, margin, big - margin, big - margin), radius=int(big * 0.2), fill=255
    )
    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)

    # Seta para baixo + bandeja, em branco.
    draw = ImageDraw.Draw(icon)
    white = (255, 255, 255, 255)
    cx = big / 2
    stroke = big * 0.075
    top, tip = big * 0.25, big * 0.60
    draw.rounded_rectangle(
        (cx - stroke / 2, top, cx + stroke / 2, tip - stroke * 0.2), radius=stroke / 2, fill=white
    )
    head = big * 0.17
    for direction in (-1, 1):
        # Cada lado da ponta da seta é um traço grosso com pontas arredondadas.
        x0, y0 = cx, tip
        x1, y1 = cx + direction * head, tip - head
        draw.line((x0, y0, x1, y1), fill=white, width=int(stroke))
        for px, py in ((x0, y0), (x1, y1)):
            draw.ellipse((px - stroke / 2, py - stroke / 2, px + stroke / 2, py + stroke / 2), fill=white)
    tray_y = big * 0.72
    left, right = big * 0.27, big * 0.73
    draw.rounded_rectangle(
        (left, tray_y - stroke / 2, right, tray_y + stroke / 2), radius=stroke / 2, fill=white
    )

    # Sombra discreta embaixo do ícone.
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    shadow_mask = mask.filter(ImageFilter.GaussianBlur(big * 0.02))
    shadow.putalpha(shadow_mask.point(lambda v: int(v * 0.35)))
    shadow = shadow.transform(shadow.size, Image.Transform.AFFINE, (1, 0, 0, 0, 1, -big * 0.012))
    result = Image.alpha_composite(shadow, icon)
    return result.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    icon = make_icon()
    icon.save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    icon.save(ASSETS / "icon.icns")
    print("Ícones gerados em", ASSETS)


if __name__ == "__main__":
    main()
