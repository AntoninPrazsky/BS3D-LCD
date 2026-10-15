"""A plain 1-bit test screen for checking the wiring, orientation and contrast."""

import math
from datetime import datetime

from PIL import Image, ImageDraw

from ..scene import Scene, text_centered


def draw_test(draw, w, h, panel, t, duration, frame, fps, now):
    """One frame of the test screen; t is seconds since the start."""
    small, big = panel.small, panel.big

    # Border on the outermost pixels: every side must be visible, else the
    # column offset or orientation is wrong. The block in the top-left corner
    # shows which way up the picture is.
    draw.rectangle((0, 0, w - 1, h - 1), outline="white")
    draw.rectangle((2, 2, 5, 5), fill="white")

    text_centered(draw, 2, "ST7565 Test", small, w)

    clock = now.strftime("%H:%M:%S")
    clock_font = big if draw.textlength(clock, font=big) <= w - 4 else small
    text_centered(draw, 14, clock, clock_font, w)

    # A ball bouncing between the side walls, bobbing on a sine wave.
    r = 3
    lane = w - 2 * (r + 2)
    pos = (t * 60) % (2 * lane)
    x = r + 2 + (pos if pos < lane else 2 * lane - pos)
    y = 36 + round(2 * math.sin(t * 6))
    draw.ellipse((x - r, y - r, x + r, y + r), fill="white")

    draw.text((4, 42), f"#{frame:<5d}{fps:4.1f} fps", font=small, fill="white")

    # Progress bar for the remaining test time.
    x0, x1, y0, y1 = 4, w - 5, h - 9, h - 4
    draw.rectangle((x0, y0, x1, y1), outline="white")
    filled = x0 + round((x1 - x0) * min(t / duration, 1.0))
    if filled > x0:
        draw.rectangle((x0, y0, filled, y1), fill="white")


def test(panel, duration=10.0, fps=25, now=datetime.now, **_):
    """Border, clock, bouncing ball, frame counter and progress bar, no greyscale."""
    w, h = panel.width, panel.height

    def render(t, n):
        img = Image.new("1", (w, h))
        draw_test(ImageDraw.Draw(img), w, h, panel, t, duration, n, n / t if t else 0.0,
                  now())
        return img
    return Scene("test", "border, clock, bouncing ball, frame counter", render, fps,
                 shots=(("", 0.3 * duration),), dithered=False)
