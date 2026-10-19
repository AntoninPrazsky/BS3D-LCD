"""Screenshots of the scenes, rendered without the hardware.

Each scene's main shot comes in three versions:

- ``NAME-frame.png``: one 1-bit frame, exactly what goes over SPI;
- ``NAME-gray.png``: the greyscale the eye builds out of the flicker: the
  average of a whole dithering cycle;
- ``NAME.png``: that greyscale as the panel shows it: tall pixels with gaps
  between them, blue-black on the yellow-green STN background, each pixel
  casting a soft shadow on the reflector behind the liquid crystal.

Further shots of a scene get only the LCD version, and ``NAME.gif`` animates
it, fades and blinks included.
"""

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from . import scenes

# Colours of the OPEN-SMART 2.4" panel, taken from photos (brightened alike):
# the yellow-green background, a half-dark pixel, which turns teal on the way,
# and a fully dark one, blue-black. In the photos a pixel is about as dark as
# its share of on-time, so the greyscale is shown as it is.
LCD_COLORS = ((125, 144, 24), (55, 90, 55), (9, 26, 36))
GAP = 0.18         # gap between pixels, as a share of the pixel pitch
SHADOW = 0.3       # how dark a pixel's shadow on the reflector is
BEZEL = (34, 34, 36)


def average(frames):
    """What 1-bit frames shown in quick succession average to (mode "L", 255 = always on)."""
    total = [sum(px) // len(frames)
             for px in zip(*(frame.convert("L").tobytes() for frame in frames))]
    return Image.frombytes("L", frames[0].size, bytes(total))


def frames_at(scene, panel, times):
    """For each of the increasing ``times``: one 1-bit frame and what the scene
    averages to there. Earlier frames are rendered too, for scenes with state."""
    # Dithered scenes redraw 30 times a second; plain ones count their frames.
    step = 1 / (30 if scene.dithered or not scene.max_fps else scene.max_fps)
    n = 0
    for t in times:
        while n * step < t:
            scene.render(n * step, n)
            n += 1
        if scene.dithered:
            cycle = [scene.render(t, n + k) for k in range(panel.dither.phases)]
            yield cycle[0], average(cycle)
        else:
            frame = scene.render(t, n)
            yield frame, frame.convert("L")


def pixel_size(aspect, pitch):
    """Width and height of one panel pixel in the screenshot."""
    return pitch, round(pitch / aspect)


def at_level(duty, level):
    """How dark the panel shows each pixel's share of on-time, 0-255, at the drive
    voltage ``level`` of ``ST7565.set_level()``, roughly: lit pixels fade out
    towards 0.8, the background greys above 1."""
    if level == 1.0:
        return duty
    gain = min(max((level - 0.8) / 0.2, 0.0), 1.0)
    fog = max(level - 1.0, 0.0) * 1.5
    return duty.point(lambda v: round(255 * min(gain * v / 255 + fog, 1.0)))


def plain(image, aspect, pitch=10):
    """A frame or greyscale (255 = darkest) scaled up with crisp, correctly shaped
    pixels, dark on white."""
    px, py = pixel_size(aspect, pitch)
    gray = image.convert("L").point(lambda v: 255 - v)
    return gray.resize((image.width * px, image.height * py), Image.NEAREST)


def lcd(duty, aspect, pitch=10, colors=LCD_COLORS, level=1.0):
    """``duty`` (mode "L", 255 = always on) as the panel shows it, in a bezel."""
    bg, mid, ink = colors
    w, h = duty.size
    px, py = pixel_size(aspect, pitch)
    W, H = w * px, h * py
    gap = max(1, round(GAP * pitch))

    # How dark each pixel's liquid crystal turns, then the pixel cells: the
    # cell grid masks it into separate tall rectangles.
    dark = at_level(duty, level).resize((W, H), Image.NEAREST)
    cell = Image.new("L", (px, py))
    ImageDraw.Draw(cell).rectangle((0, 0, px - 1 - gap, py - 1 - gap), fill=255)
    cells = Image.new("L", (W, H))
    for y in range(0, H, py):
        for x in range(0, W, px):
            cells.paste(cell, (x, y))
    pixels = ImageChops.multiply(dark, cells).filter(ImageFilter.GaussianBlur(0.35 * pitch / 10))

    # The shadow falls downwards, onto the reflector (shifted, not wrapped round).
    shadow = Image.new("L", pixels.size)
    shadow.paste(pixels, (round(0.15 * px), round(0.3 * py)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(0.45 * pitch)).point(
        lambda v: round(v * SHADOW))
    alpha = ImageChops.screen(pixels, shadow)

    # Glass a few pixels wider than the picture.
    margin = 4 * pitch
    gw, gh = W + 2 * margin, H + 2 * margin
    layer = Image.new("L", (gw, gh))
    layer.paste(alpha, (margin, margin))
    glass = ImageOps.colorize(layer, bg, ink, mid)

    # A dark bezel with rounded corners around the glass.
    border = 3 * pitch
    out = Image.new("RGBA", (gw + 2 * border, gh + 2 * border), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, out.width - 1, out.height - 1),
                                          radius=2 * pitch, fill=BEZEL)
    mask = Image.new("L", (gw, gh))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, gw - 1, gh - 1), radius=pitch // 2,
                                           fill=255)
    out.paste(glass, (border, border), mask)
    return out


def palette(image):
    """The LCD look has a few hundred colours; 128 look the same and the PNG
    gets about six times smaller."""
    return image.quantize(128, Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)


def save_gif(frames, path, fps, colors=128):
    """RGBA frames as a looping GIF with one palette, transparent outside the bezel."""
    key = (255, 0, 255)
    rgb = []
    for frame in frames:
        flat = Image.new("RGB", frame.size, key)
        flat.paste(frame, mask=frame.getchannel("A"))
        rgb.append(flat)
    # One palette for all frames, else unchanged areas shift colour between them.
    sample = rgb[::max(len(rgb) // 12, 1)]
    strip = Image.new("RGB", (rgb[0].width, rgb[0].height * len(sample)))
    for i, frame in enumerate(sample):
        strip.paste(frame, (0, i * frame.height))
    pal = strip.quantize(colors, Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rgb_pal = pal.getpalette()[:3 * colors]
    clear = min(range(colors), key=lambda i: sum((a - b) ** 2
                                                for a, b in zip(rgb_pal[3 * i:3 * i + 3], key)))
    quantized = [frame.quantize(palette=pal, dither=Image.Dither.NONE) for frame in rgb]
    quantized[0].save(path, save_all=True, append_images=quantized[1:], loop=0,
                      duration=round(1000 / fps), transparency=clear, disposal=1,
                      optimize=True)


def animation(factory, panel, length, fps=25, pitch=5, colors=LCD_COLORS, fade=0.4,
              fade_from=0.8, **options):
    """LCD-look frames of a scene's first ``length`` seconds, fading out at the end
    (and in at the start, unless the scene makes its own entrance) as the demo does."""
    scene = factory(panel, **options)
    times = [k / fps for k in range(round(length * fps))]
    frames = []
    for t, (_, duty) in zip(times, frames_at(scene, panel, times)):
        ramp = (length - t) / fade if fade else 1.0
        if fade and not scene.level:
            ramp = min(ramp, t / fade)
        if ramp < 1:
            level = fade_from + (1 - fade_from) * max(ramp, 0.0)
        else:
            level = scene.level(t) if scene.level else 1.0
        frames.append(lcd(duty, panel.aspect, pitch, colors, level))
    return frames


def write(out_dir, names, panel, pitch=10, colors=LCD_COLORS, gifs=("logo",), gif_length=4.6,
          **options):
    """Write the shots of the named scenes into ``out_dir``, and animations of those
    in ``gifs``; returns the file names."""
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def save(image, name):
        image.save(os.path.join(out_dir, name), optimize=True)
        written.append(name)

    for name in names:
        factory = scenes.SCENES[name]
        for i, (suffix, t) in enumerate(factory(panel, **options).shots):
            base = f"{name}-{suffix}" if suffix else name
            [(frame, duty)] = frames_at(factory(panel, **options), panel, [t])
            save(palette(lcd(duty, panel.aspect, pitch, colors)), f"{base}.png")
            if i == 0:
                save(plain(duty, panel.aspect, pitch), f"{base}-gray.png")
                save(plain(frame, panel.aspect, pitch), f"{base}-frame.png")
        if name in gifs:
            save_gif(animation(factory, panel, gif_length, pitch=pitch // 2, colors=colors,
                               **options), os.path.join(out_dir, f"{name}.gif"), 25)
            written.append(f"{name}.gif")
    return written
