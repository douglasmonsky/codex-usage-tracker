"""Generate repository preview artwork.

The images are built from exact rendered text and existing synthetic dashboard
screenshots so marketing copy stays crisp and reproducible.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
SOCIAL_OUT = ASSETS / "social-preview.png"
README_OUT = ASSETS / "readme-hero.png"
W, H = 1280, 640


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    candidates = {
        "regular": [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ],
        "bold": [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ],
        "black": [
            "/System/Library/Fonts/Supplemental/Arial Black.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ],
    }[weight]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_rounded(base: Image.Image, image: Image.Image, xy: tuple[int, int], radius: int) -> None:
    base.paste(image, xy, rounded_mask(image.size, radius))


def draw_soft_shadow(
    base: Image.Image, box: tuple[int, int, int, int], radius: int, alpha: int = 44
) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle((x0, y0 + 12, x1, y1 + 18), radius=radius, fill=(15, 23, 42, alpha))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))


def cover_crop(path: Path, size: tuple[int, int], focus_y: float = 0.35) -> Image.Image:
    src = Image.open(path).convert("RGBA")
    target_w, target_h = size
    scale = max(target_w / src.width, target_h / src.height)
    resized = src.resize(
        (int(src.width * scale), int(src.height * scale)), Image.Resampling.LANCZOS
    )
    left = max(0, (resized.width - target_w) // 2)
    top = int(max(0, resized.height - target_h) * focus_y)
    return resized.crop((left, top, left + target_w, top + target_h))


def draw_grid(draw: ImageDraw.ImageDraw) -> None:
    for x in range(-80, W + 80, 40):
        color = (214, 221, 235, 82) if x % 120 else (196, 205, 222, 110)
        draw.line((x, 0, x + 210, H), fill=color, width=1)
    for y in range(32, H, 42):
        draw.line((0, y, W, y), fill=(226, 231, 240, 88), width=1)


def make_base() -> Image.Image:
    base = Image.new("RGBA", (W, H), (246, 248, 252, 255))
    px = base.load()
    if px is None:
        raise RuntimeError("Could not access image pixels")
    for y in range(H):
        for x in range(W):
            nx = x / (W - 1)
            ny = y / (H - 1)
            px[x, y] = (
                int(248 - 14 * nx + 6 * ny),
                int(250 - 10 * nx + 3 * ny),
                int(253 - 2 * nx - 7 * ny),
                255,
            )

    draw = ImageDraw.Draw(base)
    draw_grid(draw)
    draw.polygon([(820, 0), (1280, 0), (1280, 640), (730, 640)], fill=(226, 235, 255, 168))
    draw.polygon([(982, 0), (1280, 0), (1280, 640), (890, 640)], fill=(218, 247, 238, 118))
    return base


def draw_dashboard_stack(base: Image.Image, *, x: int, y: int) -> None:
    draw = ImageDraw.Draw(base)
    card_box = (x, y, x + 536, y + 436)
    draw_soft_shadow(base, card_box, 30, 72)
    draw.rounded_rectangle(
        card_box, radius=30, fill=(255, 255, 255, 246), outline=(202, 213, 232), width=2
    )

    overview = cover_crop(ASSETS / "dashboard-insights.png", (486, 178), 0.20)
    calls = cover_crop(ASSETS / "dashboard-calls.png", (232, 174), 0.56)
    investigator = cover_crop(ASSETS / "dashboard-call-investigator.png", (232, 174), 0.34)

    paste_rounded(base, overview, (x + 25, y + 32), 20)
    paste_rounded(base, calls, (x + 25, y + 232), 18)
    paste_rounded(base, investigator, (x + 279, y + 232), 18)
    draw.rounded_rectangle(
        (x + 25, y + 32, x + 511, y + 210), radius=20, outline=(213, 224, 240), width=2
    )
    draw.rounded_rectangle(
        (x + 25, y + 232, x + 257, y + 406), radius=18, outline=(213, 224, 240), width=2
    )
    draw.rounded_rectangle(
        (x + 279, y + 232, x + 511, y + 406), radius=18, outline=(213, 224, 240), width=2
    )

    draw.rounded_rectangle((x + 34, y + 44, x + 178, y + 72), radius=14, fill=(37, 99, 235, 232))
    draw.text((x + 52, y + 49), "Overview", font=font(16, "bold"), fill=(255, 255, 255))
    draw.rounded_rectangle((x + 34, y + 244, x + 126, y + 270), radius=13, fill=(15, 23, 42, 228))
    draw.text((x + 51, y + 249), "Calls", font=font(15, "bold"), fill=(255, 255, 255))
    draw.rounded_rectangle((x + 288, y + 244, x + 426, y + 270), radius=13, fill=(6, 95, 70, 224))
    draw.text((x + 304, y + 249), "Investigator", font=font(15, "bold"), fill=(255, 255, 255))


def draw_stat_badge(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    label: str,
    value: str,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
) -> int:
    x, y = xy
    label_font = font(18, "bold")
    value_font = font(30, "black")
    width = (
        max(
            int(draw.textlength(label, font=label_font)),
            int(draw.textlength(value, font=value_font)),
        )
        + 54
    )
    draw.rounded_rectangle(
        (x, y, x + width, y + 96), radius=22, fill=fill, outline=outline, width=2
    )
    draw.text((x + 26, y + 18), label, font=label_font, fill=(72, 83, 104))
    draw.text((x + 26, y + 44), value, font=value_font, fill=(18, 28, 45))
    return width


def draw_title(draw: ImageDraw.ImageDraw, *, x: int, y: int) -> None:
    draw.text((x, y), "Codex Usage", font=font(76, "black"), fill=(15, 23, 42))
    draw.text((x, y + 76), "Tracker", font=font(86, "black"), fill=(37, 99, 235))
    draw.text(
        (x + 6, y + 176),
        "Unofficial local analytics for Codex tokens,",
        font=font(28, "bold"),
        fill=(53, 65, 85),
    )
    draw.text(
        (x + 6, y + 212), "cache, threads, and spend.", font=font(28, "bold"), fill=(53, 65, 85)
    )


def draw_social_preview() -> Image.Image:
    base = make_base()
    draw = ImageDraw.Draw(base)
    draw_dashboard_stack(base, x=662, y=82)

    draw.rounded_rectangle(
        (72, 70, 206, 112), radius=21, fill=(238, 246, 255), outline=(177, 199, 232), width=2
    )
    draw.text((94, 82), "MIT License", font=font(17, "bold"), fill=(31, 55, 88))
    draw.rounded_rectangle(
        (224, 70, 394, 112), radius=21, fill=(238, 253, 246), outline=(161, 218, 195), width=2
    )
    draw.text((246, 82), "10K+ downloads", font=font(17, "bold"), fill=(20, 83, 45))

    draw_title(draw, x=72, y=150)

    x = 72
    x += draw_stat_badge(draw, (x, 414), "PACKAGE", "PyPI", (255, 255, 255), (203, 213, 225)) + 18
    x += draw_stat_badge(draw, (x, 414), "DOWNLOADS", "10K+", (240, 253, 244), (134, 239, 172)) + 18
    draw_stat_badge(draw, (x, 414), "LICENSE", "MIT", (239, 246, 255), (147, 197, 253))

    draw.line((80, 558, 1188, 558), fill=(203, 213, 225), width=2)
    draw.text(
        (82, 582), "douglasmonsky/codex-usage-tracker", font=font(22, "bold"), fill=(30, 41, 59)
    )
    draw.text((825, 582), "Local dashboard + MCP tools", font=font(22, "bold"), fill=(71, 85, 105))
    return base


def draw_readme_hero() -> Image.Image:
    base = make_base()
    draw = ImageDraw.Draw(base)
    draw_dashboard_stack(base, x=662, y=82)

    draw.rounded_rectangle(
        (72, 76, 324, 118), radius=21, fill=(238, 246, 255), outline=(177, 199, 232), width=2
    )
    draw.text((96, 88), "Local-first Codex analytics", font=font(17, "bold"), fill=(31, 55, 88))

    draw_title(draw, x=72, y=158)

    bullets = [
        "Aggregate-only dashboard",
        "Thread, call, cache, and usage-drain views",
        "CLI reports plus companion MCP tools",
    ]
    for index, text in enumerate(bullets):
        bullet_y = 432 + index * 42
        draw.ellipse((80, bullet_y + 8, 94, bullet_y + 22), fill=(37, 99, 235))
        draw.text((110, bullet_y), text, font=font(24, "bold"), fill=(30, 41, 59))

    draw.line((80, 580, 1188, 580), fill=(203, 213, 225), width=2)
    draw.text(
        (82, 602), "douglasmonsky/codex-usage-tracker", font=font(22, "bold"), fill=(30, 41, 59)
    )
    draw.text((832, 602), "Private logs stay local", font=font(22, "bold"), fill=(71, 85, 105))
    return base


def save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, quality=95, optimize=True)
    print(path)


def main() -> None:
    save(draw_social_preview(), SOCIAL_OUT)
    save(draw_readme_hero(), README_OUT)


if __name__ == "__main__":
    main()
