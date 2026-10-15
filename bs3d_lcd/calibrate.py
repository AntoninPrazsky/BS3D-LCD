"""Calibration screens: contrast sweeps and side-by-side greyscale settings."""

import time

from PIL import Image, ImageDraw

from .scene import Panel, Scene, play, still, text_centered

COMPARE_VALUES = {
    "fps": (40, 60, 80, 120, 200, 0),
    "phases": (16, 8, 4, 2, 1),
    "gamma": (1.0, 0.8, 0.65, 0.5, 0.4),
}


def sweep_frame(panel, contrast, ratio):
    w, h = panel.width, panel.height
    img = Image.new("1", (w, h))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w - 1, h - 1), outline="white")
    text_centered(draw, 3, f"contrast {contrast:#04x}", panel.small, w)
    text_centered(draw, 15, f"ratio {ratio}", panel.small, w)
    # Solid block, checkerboard and empty block: at the right contrast the
    # solid one is black, the empty one stays clear and the checkerboard grey.
    size, top = 20, h - 26
    left = (w - 3 * size - 8) // 2
    draw.rectangle((left, top, left + size - 1, top + size - 1), fill="white")
    cx = left + size + 4
    for yy in range(top, top + size):
        for xx in range(cx, cx + size):
            if (xx + yy) % 2 == 0:
                draw.point((xx, yy), fill="white")
    ex = cx + size + 4
    draw.rectangle((ex, top, ex + size - 1, top + size - 1), outline="white")
    return img


def run_sweep(device, panel, what, contrast, ratio, step=4, hold=1.5):
    """Step the contrast (or the ratio) through its range, showing the values."""
    if what == "ratio":
        print(f"Ratio sweep at contrast {contrast:#04x}: note the ratio where the solid "
              "block is black and the empty one clear.")
        settings = [(contrast, r) for r in range(8)]
    else:
        print(f"Contrast sweep at ratio {ratio}: note the value where the solid block is "
              "black, the empty one clear and the text sharpest.")
        settings = [(c, ratio) for c in range(0, 0x40, step)]
    for c, r in settings:
        device.set_ratio(r)
        device.contrast(c)
        device.display(sweep_frame(panel, c, r))
        print(f"  contrast {c:#04x} ({c}), ratio {r}", flush=True)
        time.sleep(hold)


def compare_scene(panel, label):
    """A labelled smooth ramp over 8 flat grey steps, for comparing dither settings."""
    w, h = panel.width, panel.height
    gray = Image.new("L", (w, h))
    ramp_top, ramp_h = 13, 24
    ramp = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize((w, ramp_h))
    gray.paste(ramp, (0, ramp_top))
    steps, step_top = 8, ramp_top + ramp_h + 3
    draw = ImageDraw.Draw(gray)
    for i in range(steps):
        draw.rectangle((i * w // steps, step_top, (i + 1) * w // steps - 1, h - 1),
                       fill=round(i * 255 / (steps - 1)))

    render = still(panel, gray)
    frames = []
    for n in range(panel.dither.phases):
        frame = render(0, n).copy()
        text_centered(ImageDraw.Draw(frame), 1, label, panel.small, w)
        frames.append(frame)
    return Scene("compare", label, lambda t, n: frames[n % len(frames)], panel.gray_fps)


def run_compare(device, panel, what, values=None, hold=6.0):
    """Step one greyscale setting (fps, phases or gamma) through a range of values,
    labelled on the display."""
    values = values or COMPARE_VALUES[what]
    if what != "gamma":
        values = [int(v) for v in values]
    settings = {"gray_fps": panel.gray_fps, "phases": panel.dither.phases,
                "gamma": panel.dither.gamma}
    key = "gray_fps" if what == "fps" else what
    for i, value in enumerate(values, 1):
        shown = "max" if what == "fps" and value == 0 else value
        label = f"{what} {shown}  {i}/{len(values)}"
        trial = Panel(panel.width, panel.height, panel.aspect, **{**settings, key: value})
        print(f"{label}: fps {trial.gray_fps or 'max'}, phases {trial.dither.phases}, "
              f"gamma {trial.dither.gamma}", flush=True)
        frames, fps = play(device, compare_scene(trial, label), hold)
        print(f"  {fps:.0f} fps", flush=True)
