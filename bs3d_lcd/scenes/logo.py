"""The BS3D startup logo, animated."""

import math
from importlib.resources import files

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from ..greyscale import Canvas
from ..scene import Scene, animated, blink_after

# Images/logo/bs3d-logo-2048.png from the BS3D game repository (the game's
# startup logo), trimmed and scaled to 512 px wide.
LOGO = files("bs3d_lcd") / "assets" / "bs3d-logo.png"
# The round "3D" badge in that image, keyline included: centre x, centre y,
# radius, as fractions of the image width, height and width.
LOGO_BADGE = (0.495, 0.807, 0.116)


def load_logo(path, w, h, aspect, scale=1):
    """The logo as greyscale (255 = darkest), as large as fits the panel at its true
    shape, centred on a ``scale`` x panel-size image; plus where it sits on it."""
    with Image.open(path) as src:
        src = src.convert("RGBA")
    fit = min(w / src.width, h / aspect / src.height)
    size = (round(src.width * fit * scale), round(src.height * fit * aspect * scale))
    logo = src.resize(size, Image.LANCZOS)
    flat = Image.new("RGBA", size, "white")
    flat.alpha_composite(logo)
    gray = ImageOps.autocontrast(ImageOps.invert(flat.convert("L")), cutoff=1)
    full = Image.new("L", (w * scale, h * scale))
    left, top = (w * scale - size[0]) // 2, (h * scale - size[1]) // 2
    full.paste(gray, (left, top))
    return full, (left / scale, top / scale, size[0] / scale, size[1] / scale)


def logo(panel, blink=1.1, **_):
    """BS3D startup: a bubble shot up pops, its ring reveals the title, the "3D"
    badge springs in and the panel blinks; then a glint runs over it now and then."""
    w, h, aspect = panel.width, panel.height, panel.aspect
    shot, reveal, pop, pulse = 0.45, 0.8, 0.6, 0.6   # phase lengths in s
    badge_at = shot + reveal
    blink_at = badge_at + pop
    shine_from, shine_every, shine_time = blink_at + pulse + 0.4, 3.0, 0.7

    picture, (left, top, lw, lh) = load_logo(LOGO, w, h, aspect)
    hires, _ = load_logo(LOGO, w, h, aspect, Canvas.SS)
    bx, by, br = LOGO_BADGE
    # A little extra radius takes the badge's soft edge along.
    bx, by, br = left + bx * lw, top + by * lh, br * lw * 1.06
    # The title without the badge, which springs in by itself later.
    hole = panel.canvas()
    hole.circle(bx, by, br, fill=255)
    title = Image.composite(Image.new("L", (w, h)), picture, hole.image())
    s = Canvas.SS
    badge_box = tuple(round(v * s) for v in (bx - br, by - br * aspect,
                                             bx + br, by + br * aspect))
    badge = hires.crop(badge_box)
    badge_mask = Canvas.disc(*badge.size)
    # The bubble pops in the middle of the title; the ring grows until it
    # has passed the furthest corner.
    ox, oy = w / 2, top + 0.36 * lh
    reach = math.hypot(max(ox, w - ox), max(oy, h - oy) / aspect) + 2

    def draw(t):
        if t < shot:
            c = panel.canvas()
            rise = 1 - (1 - t / shot) ** 2
            c.ball(ox, h + 6 - (h + 6 - oy) * rise, 4, lo=40, hi=220)
            return c.image()

        if t >= badge_at + pop:
            return shine(t, picture)

        p = min((t - shot) / reveal, 1)
        radius = 4 + (reach - 4) * (1 - (1 - p) ** 3)
        window = panel.canvas()
        window.circle(ox, oy, radius, fill=255)
        gray = Image.composite(title, Image.new("L", (w, h)), window.image())
        if p < 1:
            ring = panel.canvas()
            ring.circle(ox, oy, radius, outline=round(220 * (1 - p)), width=1.5)
            gray = ImageChops.lighter(gray, ring.image())

        if t >= badge_at:
            # Spring in: overshoot to about 1.3x, settle at full size.
            q = min((t - badge_at) / pop, 1)
            k = 1 - (1 - q) ** 2 * math.cos(3 * math.pi * q)
            size = (round(badge.width * k / s), round(badge.height * k / s))
            if min(size) > 0:
                img = badge.resize(size, Image.LANCZOS)
                mask = badge_mask.resize(size, Image.LANCZOS)
                gray.paste(img, (round(bx - size[0] / 2), round(by - size[1] / 2)), mask)
        return gray

    def shine(t, gray):
        since = t - shine_from
        if since < 0 or since % shine_every >= shine_time:
            return gray
        # A slanted light band sweeping left to right.
        x = -24 + (w + 48) * (since % shine_every) / shine_time
        band = Image.new("L", (w, h))
        ImageDraw.Draw(band).polygon([(x, 0), (x + 9, 0), (x - 11, h), (x - 20, h)], fill=130)
        return ImageChops.subtract(gray, band.filter(ImageFilter.GaussianBlur(1.5)))

    return Scene("logo", "BS3D startup logo: bubble shot, pop reveal, 3D badge, blink, glint",
                 animated(panel, draw), panel.gray_fps, blink_after(blink_at, pulse, blink),
                 shots=(("", 2.6), ("1-shot", 0.3), ("2-reveal", 0.85), ("3-badge", 1.45),
                        ("4-glint", shine_from + 0.4 * shine_time)), gray=draw)
