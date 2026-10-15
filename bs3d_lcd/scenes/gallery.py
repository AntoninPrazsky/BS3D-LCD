"""Greyscale demo scenes: what temporal dithering can do on a 1-bit panel."""

import math
import random

from PIL import Image

from ..greyscale import gradient_backdrop
from ..scene import Scene, animated, still


def gradient(panel, **_):
    """Three light-to-dark ramps: static Bayer, static Floyd-Steinberg, FRC."""
    w, h, dither = panel.width, panel.height, panel.dither
    band = (h - 4) // 3
    ramp = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize((w, band))
    gray = Image.new("L", (w, h))
    tops = [0, band + 2, 2 * (band + 2)]
    for top in tops:
        gray.paste(ramp, (0, top))
    static = dither.frame(gray, 0)
    floyd = dither.correct(gray).convert("1")    # Pillow dithers with Floyd-Steinberg here

    # The picture doesn't move, so all dithering phases are built up front.
    frames = []
    for n in range(dither.phases):
        frame = dither.frame(gray, n)
        frame.paste(static.crop((0, tops[0], w, tops[0] + band)), (0, tops[0]))
        frame.paste(floyd.crop((0, tops[1], w, tops[1] + band)), (0, tops[1]))
        frames.append(frame)

    return Scene("gradient", "light-to-dark ramp: top static Bayer, middle static "
                 "Floyd-Steinberg, bottom temporal dithering (FRC)",
                 lambda t, n: frames[n % len(frames)], panel.gray_fps)


def sphere(panel, **_):
    """A shaded ball bouncing over a gradient."""
    w, h = panel.width, panel.height
    r = 13
    ry = r * panel.aspect
    backdrop = gradient_backdrop(w, h, 64)
    floor = h - 3

    def draw(t):
        lane = w - 2 * r
        pos = (t * 35) % (2 * lane)
        x = r + (pos if pos < lane else 2 * lane - pos)
        hop = abs(math.sin(t * math.pi / 1.2))
        y = floor - ry - (floor - 2 * ry - 2) * hop
        c = panel.canvas(backdrop)
        c.ellipse(x, floor - 1, r * (1.1 - 0.5 * hop), 2, fill=round(170 - 80 * hop))
        c.ball(x, y, r)
        return c.image()

    return Scene("sphere", "shaded ball bouncing over a gradient, all temporal dithering",
                 animated(panel, draw), panel.gray_fps, shots=(("", 1.6),))


def circles(panel, **_):
    """A still gallery of ten circle styles in two rows."""
    c = panel.canvas()
    r = 11
    xs = [13 + i * 25.5 for i in range(5)]
    top, bottom = 16, 47

    c.circle(xs[0], top, r - 0.5, outline=255)                    # thin outline
    c.circle(xs[1], top, r - 1.5, outline=170, width=3)           # thick grey ring
    c.circle(xs[2], top, r, fill=255)                             # flat disc, dark rim
    c.circle(xs[2], top, r - 1.2, fill=110)
    c.ball(xs[3], top, r)                                         # lit ball
    c.bubble(xs[4], top, r)                                       # glass bubble

    for i, k in enumerate((1, 0.75, 0.5, 0.25)):                  # target
        c.circle(xs[0], bottom, r * k, fill=230 if i % 2 == 0 else 30)
    c.glow(xs[1], bottom, r)                                      # soft glow
    for start, end, fill in ((-90, 30, 255), (30, 150, 150), (150, 270, 60)):
        c.pieslice(xs[2], bottom, r, start, end, fill)            # pie chart
    for k in range(12):                                           # ring of dots
        a = 2 * math.pi * k / 12
        c.circle(xs[3] + (r - 1.5) * math.cos(a),
                 bottom + (r - 1.5) * panel.aspect * math.sin(a), 1.5, fill=255)
    c.circle(xs[4], bottom, r, fill=240)                          # crescent moon
    c.circle(xs[4] + r * 0.45, bottom - r * 0.2 * panel.aspect, r * 0.9, fill=0)

    return Scene("circles", "still gallery: outline, ring, disc, ball, bubble / target, "
                 "glow, pie, dots, moon", still(panel, c.image()), panel.gray_fps)


def planet(panel, **_):
    """A turning globe with a ring and a moon passing in front and behind."""
    w, h, aspect = panel.width, panel.height, panel.aspect
    cx, cy, R = w / 2, h / 2, 16
    rng = random.Random(7)
    stars = [(rng.uniform(1, w - 1), rng.uniform(1, h - 1), rng.uniform(0, 2 * math.pi))
             for _ in range(14)]

    def draw(t):
        c = panel.canvas()
        for x, y, phase in stars:
            c.circle(x, y, 0.7, fill=round(150 + 100 * math.sin(2 * t + phase)))
        orbit = 1.3 * t
        moon = (cx + 52 * math.cos(orbit), cy + 12 * math.sin(orbit), 3.5 + math.sin(orbit))
        moon_in_front = math.sin(orbit) > 0
        if not moon_in_front:
            c.ball(*moon, lo=40, hi=200)
        c.arc(cx, cy, 29, 6, 180, 360, fill=190, width=2)      # ring, back half
        c.ball(cx, cy, R, lo=0, hi=120)
        # Meridians turn with the globe; only those on the near side show.
        for k in range(6):
            lon = math.radians(50 * t + 30 * k)
            if math.cos(lon) <= 0:
                continue
            half_width = R * abs(math.sin(lon))
            if half_width < 0.5:
                c.line([(cx, cy - R * aspect), (cx, cy + R * aspect)], 230)
            else:
                span = (-90, 90) if math.sin(lon) > 0 else (90, 270)
                c.arc(cx, cy, half_width, R * aspect, *span, fill=230)
        for lat in (-45, 0, 45):
            y = cy + R * aspect * math.sin(math.radians(lat))
            half_width = R * math.cos(math.radians(lat))
            c.line([(cx - half_width, y), (cx + half_width, y)], 200)
        c.arc(cx, cy, 29, 6, 0, 180, fill=230, width=2)        # ring, front half
        if moon_in_front:
            c.ball(*moon, lo=40, hi=200)
        return c.image()

    return Scene("planet", "turning globe with a ring and an orbiting moon, twinkling stars",
                 animated(panel, draw), panel.gray_fps, shots=(("", 0.5),))


def bubbles(panel, **_):
    """Glass bubbles rising and wobbling, popping into a ring at the top."""
    w, h, aspect = panel.width, panel.height, panel.aspect
    rng = random.Random(3)
    water = gradient_backdrop(w, h, 50)

    def spawn(y=None):
        r = rng.uniform(2.5, 8)
        return {"x": rng.uniform(r + 1, w - r - 1), "y": h + r if y is None else y, "r": r,
                "speed": rng.uniform(8, 14) + r, "wobble": rng.uniform(0.5, 2.5),
                "phase": rng.uniform(0, 2 * math.pi), "popped": None}

    bubbles = [spawn(rng.uniform(10, h)) for _ in range(9)]
    state = {"t": 0.0}

    def draw(t):
        dt, state["t"] = min(max(t - state["t"], 0.0), 0.1), t
        c = panel.canvas(water)
        for i, b in enumerate(bubbles):
            x = b["x"] + b["wobble"] * math.sin(3 * t + b["phase"])
            if b["popped"] is None:
                b["y"] -= b["speed"] * dt
                if b["y"] - b["r"] * aspect < 1:
                    b["popped"] = t
            if b["popped"] is None:
                # Darker than the gallery's bubble so it stands out from the water.
                c.bubble(x, b["y"], b["r"], inner=60, rim=255, power=2, outline=255)
                continue
            age = max(t - b["popped"], 0.0) / 0.3
            if age >= 1:
                bubbles[i] = spawn()
                continue
            fade = round(200 * (1 - age))
            c.circle(x, b["y"], b["r"] * (1 + 0.6 * age), outline=fade)
            for k in range(5):                                   # droplets
                a = 2 * math.pi * k / 5 + b["phase"]
                d = b["r"] * (1 + 1.2 * age)
                c.circle(x + d * math.cos(a), b["y"] + d * aspect * math.sin(a), 0.8,
                         fill=fade)
        return c.image()

    return Scene("bubbles", "glass bubbles rising, wobbling and popping",
                 animated(panel, draw), panel.gray_fps, shots=(("", 3.0),))
