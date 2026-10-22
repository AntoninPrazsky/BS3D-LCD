"""GPIO for luma.core on a Raspberry Pi 5.

luma.core drives the DC and RST lines through the RPi.GPIO API, which does
not work on the Pi 5 (its header GPIOs live on the RP1 chip). ``GpiodGPIO``
implements the small part of that API luma uses on top of libgpiod v2, which
works on every Raspberry Pi.
"""

import errno
import glob
import os

import gpiod
from gpiod.line import Direction, Value

# Labels of the chips carrying the 40-pin header: Pi 5, Pi 4, Pi 3 and older.
HEADER_CHIPS = ("pinctrl-rp1", "pinctrl-bcm2711", "pinctrl-bcm2835")


class GpiodGPIO:
    """The subset of the RPi.GPIO API that luma.core's spi interface uses."""

    BCM = "BCM"
    OUT = "out"
    LOW = 0
    HIGH = 1

    def __init__(self, chip_path=None, consumer="bs3d-lcd"):
        self._chip_path = chip_path or find_header_chip()
        self._consumer = consumer
        self._requests = {}

    def setmode(self, mode):
        pass

    def setwarnings(self, flag):
        pass

    def setup(self, pin, direction, initial=LOW):
        if direction != self.OUT:
            raise ValueError("only outputs are supported")
        settings = gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=Value.ACTIVE if initial else Value.INACTIVE,
        )
        try:
            self._requests[pin] = gpiod.request_lines(
                self._chip_path, consumer=self._consumer, config={pin: settings})
        except OSError as e:
            if e.errno == errno.EBUSY:
                raise SystemExit(f"GPIO{pin} is in use by another process "
                                 f"(see: gpioinfo -c {self._chip_path} {pin}). If the "
                                 "status display's service has the panel: "
                                 "sudo systemctl stop bs3d-lcd")
            raise

    def output(self, pin, value):
        self._requests[pin].set_value(pin, Value.ACTIVE if value else Value.INACTIVE)

    def cleanup(self, pins=None):
        if pins is None:
            pins = list(self._requests)
        elif isinstance(pins, int):
            pins = [pins]
        for pin in pins:
            request = self._requests.pop(pin, None)
            if request is not None:
                request.release()


def find_header_chip():
    """The gpiochip of the 40-pin header; its number changed between kernels."""
    for path in sorted(glob.glob("/dev/gpiochip*")):
        if os.path.islink(path) or not gpiod.is_gpiochip_device(path):
            continue
        with gpiod.Chip(path) as chip:
            if chip.get_info().label in HEADER_CHIPS:
                return path
    return "/dev/gpiochip0"
