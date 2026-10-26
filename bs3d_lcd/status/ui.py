"""The toolkit of the status pages (#5): fonts, icons and number formats.

Everything is drawn in greyscale (mode "L", 255 = darkest) on whole pixels.
Text is 1-bit; greys mean something: a value drawn grey is old, a bar drawn
grey is still filling. The panel's pixels are about 20 % taller than wide,
so icons are drawn wider than tall to look square.
"""

from PIL import Image

from ..font import Font

WIDTH, HEIGHT = 128, 64
GREY = 110                  # old values, secondary marks

# Icons, 1 = dark. Each is a few pixels wider than tall, to look square.
ICONS = {
    "dot": ("..###..",
            ".#####.",
            "#######",
            "#######",
            ".#####.",
            "..###.."),
    "ring": ("..###..",
             ".#...#.",
             "#.....#",
             "#.....#",
             ".#...#.",
             "..###.."),
    "warning": ("...#...",
                "..###..",
                "..#.#..",
                ".##.##.",
                ".#####.",
                "###.###"),
    "error": ("##...##",
              ".##.##.",
              "..###..",
              "..###..",
              ".##.##.",
              "##...##"),
    "check": ("......#",
              ".....##",
              "#...##.",
              "##.##..",
              ".###...",
              "..#...."),
    "star": ("...#...",
             "...#...",
             "#######",
             ".#####.",
             ".##.##.",
             "##...##"),
    "note": ("#########",
             "##.....##",
             "#.#...#.#",
             "#..#.#..#",
             "#...#...#",
             "#########"),
    "cup": ("#########",
            "#.#####.#",
            "#.#####.#",
            ".##...##.",
            "...###...",
            "....#....",
            "...###...",
            "..#####.."),
}

# The cups of the first three, gold darkest (the game's podium, BS3D#827).
CUP_SHADES = (255, 160, 95)


class UI:
    """The fonts the pages share."""

    def __init__(self):
        self.tiny = Font("5x8")             # the strip, captions, axis labels
        self.body = Font("6x10")            # labels and values
        self.bold = Font("6x10", bold=True)
        self.name = Font("7x13B")           # nicknames in the Top players roll
        self.big = Font("10x20", bold=True)  # the headline word or number


_icons = {}


def icon(name):
    """An icon's mask (mode "1")."""
    if name not in _icons:
        rows = ICONS[name]
        mask = Image.new("1", (len(rows[0]), len(rows)))
        mask.putdata([255 if c == "#" else 0 for row in rows for c in row])
        _icons[name] = mask
    return _icons[name]


def draw_icon(image, x, y, name, fill=255):
    mask = icon(name)
    image.paste(fill, (x, y), mask)
    return mask.width


def page(width=WIDTH, height=HEIGHT):
    return Image.new("L", (width, height))


def fmt_int(n):
    """1804320 -> "1 804 320", with thin spaces between the thousands."""
    return f"{n:,}".replace(",", "\u2009")


def fmt_age(seconds):
    """A compact age: 12s, 4m, 3h, 5d."""
    seconds = max(0, int(seconds))
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def fmt_span(seconds):
    """A longer span in two units: 2d 4h, 3h 12m, 12m 5s."""
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def row(image, font, y, label, value, fill=255, value_fill=None, left=1, right=None):
    """A label on the left and its value on the right, cap tops at ``y``."""
    right = image.width - 1 if right is None else right
    font.draw(image, left, y, label, fill)
    font.draw(image, right, y, value, fill if value_fill is None else value_fill, align="right")


def fit(fonts, text, width):
    """The first of ``fonts`` that draws ``text`` within ``width``, else the last."""
    for font in fonts:
        if font.width(text) <= width:
            return font
    return fonts[-1]
