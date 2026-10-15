"""Greyscale on a 1-bit LCD: temporal dithering and a supersampled canvas.

Greyscale images here use mode "L" with 255 as the darkest grey (a lit LCD
pixel), the opposite of Pillow's usual convention.
"""

from PIL import Image, ImageChops, ImageDraw


class Dither:
    """Turns greyscale into 1-bit frames with 17 grey levels.

    ``frame(gray, n)`` is ordered (Bayer 4x4) dithering whose thresholds shift
    by a bit-reversed sequence from frame to frame. With 16 phases every pixel
    meets all 16 thresholds in 16 frames, so its grey becomes the share of
    frames it is on (frame rate control, FRC), and neighbouring pixels flicker
    out of phase. Fewer phases shorten the cycle (less shimmer) and leave more
    of the grey to the spatial pattern; 1 phase is plain static ordered
    dithering. Every phase count averages to the same 17 levels.

    :param gamma: applied to the grey before dithering; below 1 darkens the
        mid-tones, which an LCD shows lighter than their on-time suggests.
    """

    BAYER4 = ((0, 8, 2, 10),
              (12, 4, 14, 6),
              (3, 11, 1, 9),
              (15, 7, 13, 5))
    SHIFTS = (0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15)
    PHASES = (1, 2, 4, 8, 16)
    ON = [0] + [255] * 255

    def __init__(self, w, h, phases=16, gamma=1.0):
        if phases not in self.PHASES:
            raise ValueError(f"phases must be one of {self.PHASES}, got {phases}")
        self.phases = phases
        self.gamma = gamma
        self._gamma = [round(255 * (v / 255) ** gamma) for v in range(256)]
        self._thresholds = []
        # Any power-of-two prefix of SHIFTS is evenly spread over 0-15.
        for shift in self.SHIFTS[:phases]:
            img = Image.new("L", (w, h))
            img.putdata([((self.BAYER4[y % 4][x % 4] + shift) % 16) * 16 + 8
                         for y in range(h) for x in range(w)])
            self._thresholds.append(img)

    def correct(self, gray):
        return gray.point(self._gamma)

    def frame(self, gray, n=0):
        # subtract() clips at 0, so a pixel is on exactly when gray > threshold.
        threshold = self._thresholds[n % self.phases]
        return ImageChops.subtract(self.correct(gray), threshold).point(self.ON, "1")


class Canvas:
    """Greyscale drawing at SS x the panel resolution, averaged down by ``image()``.

    Coordinates are panel pixels and may be fractions; edges come out soft and
    sub-pixel accurate. ``aspect`` is the panel's pixel width / pixel height:
    circles are drawn that much shorter than wide so they look round on a
    panel with tall pixels.
    """

    SS = 4
    _sprites = {}

    def __init__(self, w, h, background=0, aspect=1.0):
        self.w, self.h = w, h
        self.aspect = aspect
        if isinstance(background, Image.Image):
            self.img = background.copy()    # already at SS x the panel size
        else:
            self.img = Image.new("L", (w * self.SS, h * self.SS), background)
        self.draw = ImageDraw.Draw(self.img)

    def _box(self, cx, cy, rx, ry):
        s = self.SS
        return (round((cx - rx) * s), round((cy - ry) * s),
                round((cx + rx) * s) - 1, round((cy + ry) * s) - 1)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, width=1):
        self.draw.ellipse(self._box(cx, cy, rx, ry), fill=fill, outline=outline,
                          width=round(width * self.SS))

    def circle(self, cx, cy, r, fill=None, outline=None, width=1):
        self.ellipse(cx, cy, r, r * self.aspect, fill, outline, width)

    def arc(self, cx, cy, rx, ry, start, end, fill, width=1):
        """Part of an ellipse outline; angles in degrees, clockwise from 3 o'clock."""
        self.draw.arc(self._box(cx, cy, rx, ry), start, end, fill=fill,
                      width=round(width * self.SS))

    def pieslice(self, cx, cy, r, start, end, fill):
        self.draw.pieslice(self._box(cx, cy, r, r * self.aspect), start, end, fill=fill)

    def line(self, points, fill, width=1):
        s = self.SS
        self.draw.line([(x * s, y * s) for x, y in points], fill=fill, width=round(width * s))

    def ball(self, cx, cy, r, lo=60, hi=255):
        """A ball lit from the top left, ``lo`` in the highlight to ``hi`` at the rim."""
        def make(w, h):
            # radial_gradient() runs from 0 in the centre to 255 at the edge;
            # cropping it off-centre puts the highlight top-left.
            shade = Image.radial_gradient("L").crop((62, 62, 238, 238)).resize((w, h))
            return shade.point(lambda v: lo + v * (hi - lo) // 255), self.disc(w, h)
        self._sprite(("ball", lo, hi), make, cx, cy, r)

    def bubble(self, cx, cy, r, inner=10, rim=200, power=3, outline=None):
        """A glass bubble: clear in the middle, darker towards the rim, with a glint.

        A lower ``power`` spreads the shading further inwards.
        """
        def make(w, h):
            shade = Image.radial_gradient("L").resize((w, h))
            shade = shade.point(lambda v: inner + round((rim - inner) * (v / 255) ** power))
            ImageDraw.Draw(shade).ellipse((0.18 * w, 0.2 * h, 0.44 * w, 0.4 * h), fill=0)
            return shade, self.disc(w, h)
        self._sprite(("bubble", inner, rim, power), make, cx, cy, r)
        if outline is not None:
            self.circle(cx, cy, r - 0.4, outline=outline, width=0.75)

    def glow(self, cx, cy, r, peak=255):
        """A soft dark spot fading out towards radius ``r``."""
        def make(w, h):
            shade = Image.radial_gradient("L").resize((w, h))
            shade = shade.point(lambda v: round(peak * (1 - v / 255) ** 2))
            return shade, shade
        self._sprite(("glow", peak), make, cx, cy, r)

    def _sprite(self, key, make, cx, cy, r):
        w = round(2 * r * self.SS)
        h = round(w * self.aspect)
        key += (w, h)
        if key not in self._sprites:
            self._sprites[key] = make(w, h)
        image, mask = self._sprites[key]
        self.img.paste(image, (round(cx * self.SS - w / 2), round(cy * self.SS - h / 2)), mask)

    @staticmethod
    def disc(w, h):
        """A filled ellipse mask of the given size."""
        mask = Image.new("L", (w, h))
        ImageDraw.Draw(mask).ellipse((0, 0, w - 1, h - 1), fill=255)
        return mask

    def image(self):
        return self.img.resize((self.w, self.h), Image.BOX)


def gradient_backdrop(w, h, darkest):
    """A top-to-bottom gradient from clear to ``darkest``, at Canvas resolution."""
    s = Canvas.SS
    return Image.linear_gradient("L").resize((w * s, h * s)).point(
        lambda v: v * darkest // 255)
