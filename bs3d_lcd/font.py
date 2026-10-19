"""Pixel fonts for the panel: the X11 misc-fixed fonts, read from BDF.

The fonts are public domain ("Share and enjoy."), by Markus Kuhn and others
(https://gitlab.freedesktop.org/xorg/font/misc-misc), and every size of them
covers every letter a BS3D nickname may hold, U+0020 to U+017F.
``tools/subset_fonts.py`` cuts them to those and a few symbols.

Pillow's own bitmap fonts hold 256 characters at most, so the BDF is read
here and each glyph becomes a small 1-bit mask, pasted where it belongs. Text
is drawn on whole pixels into greyscale images (mode "L", 255 = darkest).
"""

import unicodedata
from functools import lru_cache
from importlib.resources import files

from PIL import Image, ImageChops

FONT_DIR = files("bs3d_lcd") / "assets" / "fonts"


class Glyph:
    """One character: its mask, where the mask sits and how far the pen moves.

    ``left`` and ``ink`` are the first inked column and the inked width, for
    proportional spacing; a blank glyph has ``ink`` 0.
    """

    __slots__ = ("mask", "dx", "dy", "advance", "left", "ink")

    def __init__(self, mask, dx, dy, advance):
        self.mask, self.dx, self.dy, self.advance = mask, dx, dy, advance
        box = mask.getbbox()
        self.left, self.ink = (box[0], box[2] - box[0]) if box else (0, 0)


def read_bdf(path):
    """The glyphs of a BDF font by code point, and its properties."""
    glyphs, props = {}, {}
    with open(path, encoding="latin-1") as f:
        lines = iter(f.read().splitlines())
    for line in lines:
        key, _, value = line.partition(" ")
        if key in ("FONT_ASCENT", "FONT_DESCENT", "CAP_HEIGHT", "X_HEIGHT"):
            props[key] = int(value)
        elif key == "STARTCHAR":
            code = advance = None
            for line in lines:
                key, _, value = line.partition(" ")
                if key == "ENCODING":
                    code = int(value.split()[0])
                elif key == "DWIDTH":
                    advance = int(value.split()[0])
                elif key == "BBX":
                    w, h, dx, dy = (int(v) for v in value.split())
                elif key == "BITMAP":
                    rows = [next(lines) for _ in range(h)]
                    next(lines)                     # ENDCHAR
                    break
            mask = Image.new("1", (w, h))
            if w and h:
                bits = (w + 7) // 8 * 8
                mask.putdata([255 if int(row, 16) >> (bits - 1 - x) & 1 else 0
                              for row in rows for x in range(w)])
            glyphs[code] = Glyph(mask, dx, dy, advance)
    return glyphs, props


class Font:
    """A pixel font.

    ``draw(image, x, y, text)`` puts the text's cap tops at row ``y``: capital
    letters fill rows ``y`` to ``y + cap - 1``, the baseline is under them,
    and marks on capitals and ascenders rise above ``y`` into ``ascent - cap``
    rows.

    :param proportional: letters are spaced by their ink plus ``spacing``
        instead of the font's fixed cell; digits keep the cell (tabular), so
        numbers do not jitter as they change.
    :param bold: each glyph is smeared one pixel to the right.
    """

    def __init__(self, name, proportional=True, bold=False, spacing=1, space=None):
        self.name = name
        glyphs, props = _load(name)
        self.ascent, self.descent = props["FONT_ASCENT"], props["FONT_DESCENT"]
        self.cap, self.x_height = props["CAP_HEIGHT"], props["X_HEIGHT"]
        self.proportional, self.bold, self.spacing = proportional, bold, spacing
        self.cell = glyphs[ord("0")].advance + bold
        self.space = space if space is not None else max(2, self.cell // 2)
        self._glyphs = glyphs if not bold else {c: _embolden(g) for c, g in glyphs.items()}

    def glyph(self, char):
        """The glyph for one character; letters the font lacks fall back to their
        base letter, anything else to "?"."""
        g = self._glyphs.get(ord(char))
        if g is None:
            base = unicodedata.normalize("NFKD", char)[:1]
            g = self._glyphs.get(ord(base)) if base else None
        return g or self._glyphs[ord("?")]

    def has(self, char):
        return ord(char) in self._glyphs

    def _layout(self, text):
        """(glyph, x) for every character drawn, and the total width."""
        x, out = 0, []
        for char in unicodedata.normalize("NFC", text):
            if char == " " and self.proportional:
                x += self.space
                continue
            if char == "\u2009":
                x += max(2, self.space - 1)     # a thin space, still visible when small
                continue
            g = self.glyph(char)
            if not self.proportional or char.isdigit() or not g.ink:
                out.append((g, x))
                x += g.advance
            else:
                out.append((g, x - g.left))
                x += g.ink + self.spacing
        # No spacing after the last letter.
        if out and self.proportional and not text[-1:].isdigit() and text[-1:] != " ":
            x -= self.spacing
        return out, x

    def width(self, text):
        return self._layout(text)[1]

    def draw(self, image, x, y, text, fill=255, align="left"):
        """Draw ``text`` with its cap tops at row ``y``; ``x`` is its left edge, its
        centre or its right edge for ``align`` left, center or right. Returns the
        width."""
        out, width = self._layout(text)
        if align == "center":
            x -= width // 2
        elif align == "right":
            x -= width
        baseline = y + self.cap
        for g, gx in out:
            if g.mask.width:
                top = baseline - g.dy - g.mask.height
                image.paste(fill, (x + gx + g.dx, top), g.mask)
        return width


def _embolden(g):
    w, h = g.mask.size
    if not w:
        return Glyph(g.mask, g.dx, g.dy, g.advance + 1)
    wider = Image.new("1", (w + 1, h))
    wider.paste(g.mask, (0, 0))
    shifted = Image.new("1", (w + 1, h))
    shifted.paste(g.mask, (1, 0))
    return Glyph(ImageChops.logical_or(wider, shifted), g.dx, g.dy, g.advance + 1)


@lru_cache(maxsize=None)
def _load(name):
    return read_bdf(FONT_DIR / f"{name}.bdf")


def font_names():
    return sorted(p.name[:-4] for p in FONT_DIR.iterdir() if p.name.endswith(".bdf"))
