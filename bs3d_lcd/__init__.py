"""BS3D-LCD: an ST7565 128x64 LCD on a Raspberry Pi 5 as the BS3D server's display.

An ST7565 driver for luma.core that works on the Pi 5, smooth fades through
the panel's drive voltage, greyscale on a 1-bit panel by temporal dithering,
animated scenes (the BS3D startup logo first) and screenshots that show how
they look on the LCD.
"""

__version__ = "0.1.0"
