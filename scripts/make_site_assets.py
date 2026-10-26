"""Gera os arquivos de apoio do site (pasta site/): fontes WOFF2, ícones e a
imagem de prévia usada quando o link é compartilhado (WhatsApp, redes sociais).

Uso: pip install pillow fonttools brotli && python scripts/make_site_assets.py
"""

from pathlib import Path

from fontTools import subset
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
FONTS = ROOT / "assets" / "fonts"

# Caracteres usados em português (latim básico + acentos + pontuação comum).
UNICODES = "U+0000-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2190-2199,U+2212"


def make_fonts() -> None:
    out = SITE / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for weight, name in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")):
        subset.main([
            str(FONTS / f"Inter-{name}.ttf"),
            f"--unicodes={UNICODES}",
            "--flavor=woff2",
            "--layout-features=kern,liga,calt,tnum",
            f"--output-file={out / f'inter-{weight}.woff2'}",
        ])


def make_icons() -> None:
    out = SITE / "img"
    out.mkdir(parents=True, exist_ok=True)
    icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
    for size, name in ((32, "favicon-32.png"), (180, "apple-touch-icon.png"), (192, "icon-192.png")):
        icon.resize((size, size), Image.Resampling.LANCZOS).save(out / name, optimize=True)


def make_social_card() -> None:
    width, height = 1200, 630
    card = Image.new("RGB", (width, height), (14, 15, 19))

    # Brilho colorido no fundo, nas cores do app.
    glow = Image.new("RGB", (width, height), (14, 15, 19))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-200, -300, 700, 500), fill=(92, 64, 255))
    draw.ellipse((650, 250, 1450, 950), fill=(40, 110, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    card = Image.blend(card, glow, 0.55)

    icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA").resize((220, 220), Image.Resampling.LANCZOS)
    card.paste(icon, (90, (height - 220) // 2 - 10), icon)

    draw = ImageDraw.Draw(card)
    title = ImageFont.truetype(str(FONTS / "Inter-Bold.ttf"), 76)
    subtitle = ImageFont.truetype(str(FONTS / "Inter-Medium.ttf"), 34)
    small = ImageFont.truetype(str(FONTS / "Inter-SemiBold.ttf"), 26)
    x = 350
    draw.text((x, 190), "Baixador de Vídeos", font=title, fill=(255, 255, 255))
    draw.text((x, 292), "Vídeos e músicas a partir de um link.", font=subtitle, fill=(200, 204, 222))
    draw.text((x, 340), "MP4 até 4K · MP3 com capa · playlists", font=subtitle, fill=(200, 204, 222))

    # "Pílulas" com os sistemas.
    px = x
    for label in ("Windows", "Mac", "Linux", "Grátis"):
        text_w = draw.textlength(label, font=small)
        draw.rounded_rectangle((px, 420, px + text_w + 40, 466), radius=23, fill=(38, 36, 78),
                               outline=(124, 108, 255), width=2)
        draw.text((px + 20, 428), label, font=small, fill=(235, 236, 245))
        px += text_w + 56
    card.save(SITE / "img" / "og-card.png", optimize=True)


if __name__ == "__main__":
    make_fonts()
    make_icons()
    make_social_card()
    print("Arquivos do site gerados em", SITE)
