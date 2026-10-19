"""Scenes and the loop that plays them on the panel."""

import math
import time

from PIL import ImageFont

from .greyscale import Canvas, Dither

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


class Panel:
    """What scenes draw for: the panel's size and pixel shape, greyscale settings, fonts.

    :param aspect: pixel width / pixel height. The OPEN-SMART 2.4" panel's
        128 x 64 pixels cover 43 x 26 mm (0.336 x 0.406 mm each), so 0.83.
    :param gray_fps: frame rate of the dithered scenes (0 = as fast as the
        SPI bus allows). Slower ones beat with the LCD's own refresh.
    """

    def __init__(self, width=128, height=64, aspect=0.83, phases=16, gamma=0.65,
                 gray_fps=200):
        self.width, self.height = width, height
        self.aspect = aspect
        self.gray_fps = gray_fps
        self.dither = Dither(width, height, phases, gamma)
        self.small = ImageFont.load_default_imagefont()
        try:
            self.big = ImageFont.truetype(FONT_PATH, 16)
        except OSError:
            self.big = self.small

    def canvas(self, background=0):
        return Canvas(self.width, self.height, background, self.aspect)


class Scene:
    """Something to show: ``render(t, n)`` returns the 1-bit frame for ``t`` seconds
    into the scene and frame number ``n``.

    :param max_fps: frame rate cap, 0 = as fast as the SPI bus allows.
    :param level: ``level(t)`` -> V0 level, for scenes that pulse the panel.
    :param shots: ``(suffix, t)`` moments for screenshots, the main one first.
    :param dithered: frames are greyscale dithered over time, so a screenshot
        averages a whole dithering cycle; False for plain 1-bit scenes.
    :param gray: ``gray(t)`` -> the greyscale picture before dithering, for
        scenes that the status display pushes out like a page (the logo).
    """

    def __init__(self, name, about, render, max_fps, level=None, shots=None, dithered=True,
                 gray=None):
        self.name = name
        self.about = about
        self.render = render
        self.max_fps = max_fps
        self.level = level
        self.shots = shots or (("", 2.0),)
        self.dithered = dithered
        self.gray = gray


def still(panel, gray):
    """``render`` for a greyscale picture that doesn't move: all dithering phases
    are built up front."""
    frames = [panel.dither.frame(gray, n) for n in range(panel.dither.phases)]
    return lambda t, n: frames[n % len(frames)]


def animated(panel, draw, rate=30):
    """``render`` for a greyscale animation: ``draw(t)`` is called ``rate`` times
    a second; in between only the dithering phase changes."""
    state = {"tick": None}

    def render(t, n):
        tick = int(t * rate)
        if tick != state["tick"]:
            state.update(tick=tick, gray=draw(t))
        return panel.dither.frame(state["gray"], n)
    return render


def text_centered(draw, y, text, font, width):
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) // 2 - left, y), text, font=font, fill="white")


def blink_after(start, length, peak):
    """A level curve that pulses to ``peak`` and back once, from ``start`` s on."""
    def level(t):
        if start <= t < start + length:
            return 1 + (peak - 1) * math.sin(math.pi * (t - start) / length)
        return 1.0
    return level


def play(device, scene, duration, fade=0.0, fade_from=0.8, fade_in=True, fade_out=True,
         level=None):
    """Show the scene's frames for ``duration`` s; returns the frame count and fps.

    With ``fade``, the panel fades in from ``fade_from`` over the first ``fade``
    seconds and out to it over the last, while the scene keeps moving.
    ``level(t)`` drives the panel the rest of the time.
    """
    current = None

    def update_level(t):
        nonlocal current
        ramp = 1.0
        if fade and fade_in:
            ramp = min(ramp, t / fade)
        if fade and fade_out:
            ramp = min(ramp, (duration - t) / fade)
        if ramp < 1:
            target = fade_from + (1 - fade_from) * max(ramp, 0.0)
        else:
            target = level(t) if level else 1.0
        if target != current:
            device.set_level(target)
            current = target

    start = time.monotonic()
    n = 0
    while (t := time.monotonic() - start) < duration:
        update_level(t)
        device.display(scene.render(t, n))
        n += 1
        if scene.max_fps:
            # Keep the level moving smoothly while a slow scene waits.
            next_frame = start + n / scene.max_fps
            while (now := time.monotonic()) < next_frame:
                update_level(now - start)
                time.sleep(min(0.005, next_frame - now))
    return n, n / (time.monotonic() - start)


def run_scenes(device, scenes, duration, fade=0.4, fade_from=0.8, blink=1.1, keep=False,
               loop=False):
    """Play the scenes in turn, each fading in from nothing and out again.

    The first scene pulses once (to ``blink``) right after it has faded in; a
    scene with its own level curve (the logo) makes its own entrance instead.
    ``keep`` leaves the last scene on the panel, ``loop`` repeats them forever.
    """
    first = True
    while True:
        for i, scene in enumerate(scenes):
            level = scene.level
            if first and not level and fade and blink != 1.0:
                level = blink_after(fade, fade, blink)
            first = False
            last = i == len(scenes) - 1 and not loop
            print(f"{scene.name}: {scene.about}", flush=True)
            frames, fps = play(device, scene, duration, fade, fade_from,
                               fade_in=not scene.level, fade_out=not (last and keep),
                               level=level)
            print(f"  {frames} frames in {duration:g} s ({fps:.0f} fps)", flush=True)
        if not loop:
            return
