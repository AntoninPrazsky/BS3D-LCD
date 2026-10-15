"""ST7565 driver as a luma.core device.

luma.lcd has no ST7565 class (its st7567 hard-codes the column offset and the
power-up sequence), so this one is written on top of luma.core. Anything that
draws on a luma device (``luma.core.render.canvas`` and friends) works with it.
"""

import atexit
import bisect
import os
import time

from luma.core.device import device as luma_device
from luma.core.error import DeviceNotFoundError
from luma.core.interface.serial import spi
from PIL import Image

from .gpio import GpiodGPIO

# 1 + Rb/Ra for the ST7565's internal resistor ratios 0-7.
RATIO_GAIN = (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.4)


def v0(ratio, contrast):
    """LCD drive voltage V0 for a ratio and contrast, in units of the regulator reference."""
    return RATIO_GAIN[ratio] * (1 - (63 - contrast) / 162)


# Every (V0, ratio, contrast) the chip can produce, lightest first. Fades step
# through these, which is much finer than the 64 contrast values alone.
V0_STEPS = sorted((v0(r, c), r, c) for r in range(8) for c in range(64))
V0_KEYS = [step[0] for step in V0_STEPS]


class ST7565(luma_device):
    """ST7565 monochrome LCD controller (up to 132 x 64 pixels).

    :param contrast: electronic volume, 0x00-0x3F (command 0x81).
    :param ratio: internal V0 resistor ratio, 0-7 (command 0x20-0x27). Coarse
        contrast: if no ``contrast`` value looks right, change this.
    :param bias9: LCD bias 1/9 (0xA2) if True, 1/7 (0xA3) if False.
    :param mirror_x: reverse the SEG direction (0xA1). The panel then sits at
        RAM columns 4-131, so the column offset defaults to 4.
    :param mirror_y: normal COM direction (0xC0) instead of reverse (0xC8).
    :param col_offset: first RAM column of the visible area (None = auto).
    :param invert: show white-on-black (0xA7).

    ``set_level()``, ``fade()`` and ``blink()`` lighten or darken the whole
    panel smoothly by scaling V0 relative to ``ratio`` and ``contrast``.
    """

    PAGE_ADDR = 0xB0

    def __init__(self, serial_interface, width=128, height=64, rotate=0, contrast=0x30,
                 ratio=4, bias9=True, mirror_x=False, mirror_y=False, col_offset=None,
                 invert=False):
        super().__init__(serial_interface=serial_interface)
        if not (width <= 132 and height <= 64 and height % 8 == 0):
            raise ValueError(f"ST7565 panels are up to 132 x 64 (height a multiple of 8), "
                             f"got {width} x {height}")
        self.capabilities(width, height, rotate, mode="1")
        self._pages = height // 8
        self.col_offset = (4 if mirror_x else 0) if col_offset is None else col_offset
        self._level = 1.0

        self.command(0xE2)                        # software reset
        time.sleep(0.01)
        self.command(0xA2 if bias9 else 0xA3)     # LCD bias
        self.command(0xA1 if mirror_x else 0xA0)  # SEG direction
        self.command(0xC0 if mirror_y else 0xC8)  # COM direction
        self.command(0x40)                        # display start line 0
        # Power the booster, regulator and follower up one at a time, as the
        # datasheet's power-on sequence does.
        self.command(0x2C)
        time.sleep(0.05)
        self.command(0x2E)
        time.sleep(0.05)
        self.command(0x2F)
        time.sleep(0.01)
        self.set_ratio(ratio)
        self.contrast(contrast)
        self.command(0xA7 if invert else 0xA6)
        self.command(0xA4)                        # show RAM, not all pixels on
        self.clear()
        self.show()

    def show(self):
        self.command(0xAF)

    def hide(self):
        self.command(0xAE)

    def contrast(self, level):
        if not 0 <= level <= 0x3F:
            raise ValueError(f"ST7565 contrast is 0x00-0x3F, got {level:#04x}")
        self._contrast = level
        self._level = 1.0
        self.command(0x81, level)

    def set_ratio(self, ratio):
        if not 0 <= ratio <= 7:
            raise ValueError(f"resistor ratio is 0-7, got {ratio}")
        self._ratio = ratio
        self._level = 1.0
        self.command(0x20 | ratio)

    def set_level(self, level):
        """Drive the panel at ``level`` times the V0 of the set ratio and contrast.

        1.0 is the normal picture, lower is lighter, higher is darker; the
        whole panel changes at once. The visible range is narrow: lit pixels
        fade out somewhere below 0.9 and the background turns grey above 1.1.
        """
        if level == 1.0:
            ratio, contrast = self._ratio, self._contrast
        else:
            target = level * v0(self._ratio, self._contrast)
            i = bisect.bisect_left(V0_KEYS, target)
            _, ratio, contrast = min(V0_STEPS[max(i - 1, 0):i + 1],
                                     key=lambda step: abs(step[0] - target))
        self.command(0x20 | ratio, 0x81, contrast)
        self._level = level

    def fade(self, to, duration, start=None, during=None):
        """Move the level linearly from ``start`` (default: the current one) to ``to``.

        ``during`` is called on every step, e.g. to keep drawing frames.
        """
        start = self._level if start is None else start
        t0 = time.monotonic()
        while (t := time.monotonic() - t0) < duration:
            self.set_level(start + (to - start) * t / duration)
            if during:
                during()
            else:
                time.sleep(0.005)
        self.set_level(to)

    def blink(self, peak=1.1, duration=0.6, during=None):
        """Pulse the level smoothly to ``peak`` and back to 1.0."""
        self.fade(peak, duration / 2, during=during)
        self.fade(1.0, duration / 2, during=during)

    def display(self, image):
        assert image.mode == self.mode
        assert image.size == self.size

        image = self.preprocess(image)
        # A display RAM byte is a vertical run of 8 pixels, top pixel in bit 0.
        # Rotated 90 degrees clockwise, each screen column becomes a row of 8
        # MSB-first bytes for pages 7..0, so Pillow does the bit packing.
        packed = image.transpose(Image.Transpose.ROTATE_270).tobytes()
        col = self.col_offset

        for page in range(self._pages):
            self.command(self.PAGE_ADDR | page, 0x10 | (col >> 4), col & 0x0F)
            self.data(list(packed[self._pages - 1 - page::self._pages]))


def open_display(port=0, device=0, dc=25, rst=24, spi_hz=4_000_000, gpiochip=None,
                 **options):
    """An ``ST7565`` on /dev/spidev<port>.<device>, DC and RST on BCM GPIOs.

    ``options`` go to ``ST7565``. Raises ``RuntimeError`` with a hint if SPI
    is off.
    """
    path = f"/dev/spidev{port}.{device}"
    if not os.path.exists(path):
        raise RuntimeError(f"{path} does not exist: SPI is off. Enable it with\n"
                           "  sudo raspi-config nonint do_spi 0\n"
                           "(or dtparam=spi=on in /boot/firmware/config.txt).")
    gpio = GpiodGPIO(gpiochip)
    # atexit runs in reverse order: luma's own hook (blank the display, close
    # SPI), registered by the device below, runs first; then the GPIO lines
    # are released.
    atexit.register(gpio.cleanup)
    try:
        serial = spi(gpio=gpio, port=port, device=device, bus_speed_hz=spi_hz,
                     gpio_DC=dc, gpio_RST=rst, reset_hold_time=0.01, reset_release_time=0.01)
    except DeviceNotFoundError as e:
        raise RuntimeError(f"{path}: {e}") from e
    return ST7565(serial, **options)
