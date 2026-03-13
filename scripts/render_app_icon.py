from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ICONSET_SPECS = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(_lerp(start[0], end[0], t)),
        int(_lerp(start[1], end[1], t)),
        int(_lerp(start[2], end[2], t)),
    )


def _diagonal_gradient(size: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> Image.Image:
    gradient = Image.new("RGBA", (size, size))
    pixels = gradient.load()
    span = max((size - 1) * 2, 1)
    for y in range(size):
        for x in range(size):
            t = (x + y) / span
            r, g, b = _lerp_color(start, end, t)
            pixels[x, y] = (r, g, b, 255)
    return gradient


def _radial_glow(size: int, color: tuple[int, int, int], opacity: int) -> Image.Image:
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    bounds = (-size * 0.18, -size * 0.12, size * 0.92, size * 0.82)
    draw.ellipse(bounds, fill=(*color, opacity))
    return glow.filter(ImageFilter.GaussianBlur(size // 12))


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def _apply_mask(image: Image.Image, mask: Image.Image) -> Image.Image:
    masked = Image.new("RGBA", image.size, (0, 0, 0, 0))
    masked.paste(image, (0, 0), mask)
    return masked


def _draw_card(size: tuple[int, int]) -> Image.Image:
    width, height = size
    card = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=88,
        fill=(249, 245, 238, 255),
        outline=(255, 255, 255, 215),
        width=6,
    )

    draw.rounded_rectangle((46, 44, width - 46, 104), radius=30, fill=(241, 101, 99, 255))
    draw.rounded_rectangle((46, height - 92, width - 46, height - 46), radius=24, fill=(92, 194, 239, 255))

    fold = [(width - 188, 0), (width, 0), (width, 172)]
    draw.polygon(fold, fill=(255, 201, 120, 255))
    draw.line((width - 188, 0, width - 1, 172), fill=(225, 161, 67, 220), width=5)

    amber = (246, 191, 64, 255)
    amber_dark = (218, 149, 42, 255)
    draw.rounded_rectangle((78, 166, 208, height - 138), radius=58, fill=amber)
    draw.rounded_rectangle((78, height - 220, 288, height - 138), radius=40, fill=amber)
    draw.rounded_rectangle((92, 180, 194, height - 154), radius=48, fill=(255, 215, 102, 110))
    draw.rounded_rectangle((92, height - 212, 272, height - 154), radius=34, fill=(255, 231, 170, 120))
    draw.ellipse((188, 216, 250, 278), fill=(241, 101, 99, 255))
    draw.ellipse((204, 232, 234, 262), fill=(252, 226, 209, 255))

    line_color = (24, 47, 72, 220)
    soft_line = (24, 47, 72, 138)
    draw.rounded_rectangle((272, 182, width - 84, 246), radius=28, fill=line_color)
    draw.rounded_rectangle((272, 286, width - 112, 336), radius=24, fill=soft_line)
    draw.rounded_rectangle((272, 368, width - 144, 418), radius=24, fill=soft_line)
    draw.rounded_rectangle((272, 450, width - 168, 500), radius=24, fill=soft_line)
    draw.rounded_rectangle((272, 532, width - 198, 582), radius=24, fill=soft_line)
    draw.rounded_rectangle((272, 614, width - 240, 664), radius=24, fill=soft_line)
    draw.rounded_rectangle((272, 704, width - 108, 766), radius=28, fill=(15, 85, 133, 255))

    draw.rounded_rectangle((316, 714, width - 168, 754), radius=18, fill=(255, 255, 255, 115))
    draw.ellipse((width - 124, 690, width - 72, 742), fill=(241, 101, 99, 255))
    draw.ellipse((width - 115, 699, width - 81, 733), fill=(255, 226, 214, 165))
    draw.rounded_rectangle((312, 82, 446, 118), radius=18, fill=(255, 255, 255, 115))

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((-80, -70, 320, 280), fill=(255, 255, 255, 78))
    overlay = overlay.filter(ImageFilter.GaussianBlur(46))
    return Image.alpha_composite(card, overlay)


def render_master_icon(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((120, 132, size - 120, size - 76), radius=198, fill=(7, 14, 25, 168))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(54)))

    base_size = size - 180
    gradient = _diagonal_gradient(base_size, (7, 18, 31), (10, 110, 183))
    gradient = ImageChops.screen(gradient, _radial_glow(base_size, (245, 122, 116), 108))
    gradient = Image.alpha_composite(gradient, _radial_glow(base_size, (255, 255, 255), 84))
    base_mask = _rounded_mask((base_size, base_size), 182)
    gradient = _apply_mask(gradient, base_mask)
    image.alpha_composite(gradient, (90, 90))

    border = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.rounded_rectangle(
        (2, 2, base_size - 3, base_size - 3),
        radius=182,
        outline=(255, 255, 255, 70),
        width=5,
    )
    image.alpha_composite(border, (90, 90))

    card = _draw_card((560, 780))
    card_shadow = Image.new("RGBA", (700, 900), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(card_shadow)
    shadow_draw.rounded_rectangle((80, 100, 620, 860), radius=90, fill=(5, 14, 23, 110))
    card_shadow = card_shadow.filter(ImageFilter.GaussianBlur(42))

    card_canvas = Image.new("RGBA", (700, 900), (0, 0, 0, 0))
    card_canvas.alpha_composite(card_shadow, (0, 0))
    card_canvas.alpha_composite(card, (70, 72))
    rotated_card = card_canvas.rotate(-7, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(rotated_card, ((size - rotated_card.width) // 2 + 12, (size - rotated_card.height) // 2 + 8))

    accent = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent)
    accent_draw.ellipse((0, 0, 220, 220), fill=(255, 255, 255, 28))
    accent = accent.filter(ImageFilter.GaussianBlur(6))
    image.alpha_composite(accent, (132, 146))

    return image


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    icons_dir = repo_root / "assets" / "icons"
    iconset_dir = icons_dir / "luxnews.iconset"
    icons_dir.mkdir(parents=True, exist_ok=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    master = render_master_icon()
    png_path = icons_dir / "luxnews_icon.png"
    ico_path = icons_dir / "luxnews.ico"
    icns_path = icons_dir / "luxnews.icns"
    master.save(png_path)
    master.save(
        ico_path,
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )

    for filename, size in ICONSET_SPECS:
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / filename)

    iconutil = shutil.which("iconutil")
    if iconutil:
        subprocess.run(
            [iconutil, "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=True,
        )
    else:
        print("iconutil not found; skipped .icns generation.")


if __name__ == "__main__":
    main()
