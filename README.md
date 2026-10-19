# BS3D-LCD

A 2.4" ST7565 128×64 monochrome LCD on a Raspberry Pi 5, as the front-panel display of the [BS3D](https://github.com/AntoninPrazsky/BS3D) game server (the Pi that runs [BS3D-API](https://github.com/AntoninPrazsky/BS3D-API)). It greets you with the game's animated startup logo, and is becoming the server's status display: whether the server is online, how the playing goes, and a siren when something fails ([the plan](https://github.com/AntoninPrazsky/BS3D-LCD/issues/1); it runs on made-up data for now).

<p align="center">
  <img src="docs/screenshots/logo.gif" alt="The animated BS3D startup logo on the LCD (simulated)" width="710"><br>
  <sub>The startup logo, simulated; <a href="#what-it-looks-like">photos of the real panel</a> below.</sub>
</p>

Most of it is not BS3D-specific and may be useful for any ST7565 panel on a Pi:

- **An ST7565 driver for [luma.core](https://github.com/rm-hull/luma.core) that works on the Raspberry Pi 5.** luma.lcd has no ST7565 class (its `st7567` hard-codes the column offset), and RPi.GPIO does not work on the Pi 5, so the DC and RST lines go through libgpiod instead. Anything that draws on a luma device works with it.
- **Smooth fades and blinks** of the whole panel by stepping the LCD drive voltage V0 through all 512 combinations of the chip's resistor ratio and electronic volume, far finer than the 64 contrast steps alone.
- **17 grey levels on a 1-bit panel**, by temporal dithering (frame rate control): a 4×4 Bayer matrix whose thresholds shift every frame, sent at 200 frames per second.
- **A supersampled greyscale canvas** for soft, sub-pixel-accurate shapes, with circles corrected for the panel's tall pixels.
- **Pixel fonts with every Latin letter up to U+017F**, the public-domain X11 misc-fixed fonts read from BDF, since Pillow's bitmap fonts stop at 256 characters.
- **Pages that push each other out** with an eased slide, and **an alarm** that pulses the whole panel through V0.
- **Animated scenes**, calibration screens, and **screenshots** that simulate how the panel looks, with no hardware needed.

## What it looks like

The yellow-green STN panel with its blue-black pixels looks very different from the same picture on a modern IPS or OLED screen: more "digital", more retro. Phone photos of the real thing (the camera's short exposure catches some of the greyscale flicker that the eye averages away):

| | | |
|:---:|:---:|:---:|
| <img src="docs/photos/logo.jpg" alt="logo, photo"> | <img src="docs/photos/test.jpg" alt="test, photo"> | <img src="docs/photos/circles.jpg" alt="circles, photo"> |
| <img src="docs/photos/planet.jpg" alt="planet, photo"> | <img src="docs/photos/bubbles.jpg" alt="bubbles, photo"> | <img src="docs/photos/gradient.jpg" alt="gradient, photo"> |

### Simulated screenshots

These are rendered by `bs3d-lcd screenshots`, which simulates the panel with colours and tones taken from the photos: the yellow-green background, pixels about 20 % taller than wide with gaps between them, blue-black when fully on and teal on the way there, and the soft shadow each pixel casts on the reflector behind the liquid crystal.

| | |
|:---:|:---:|
| <img src="docs/screenshots/logo.png" alt="logo"><br>`logo`: the BS3D startup logo | <img src="docs/screenshots/test.png" alt="test"><br>`test`: border, clock, frame rate (1-bit) |
| <img src="docs/screenshots/planet.png" alt="planet"><br>`planet`: turning globe, ring, orbiting moon | <img src="docs/screenshots/bubbles.png" alt="bubbles"><br>`bubbles`: rising and popping glass bubbles |
| <img src="docs/screenshots/circles.png" alt="circles"><br>`circles`: ten circle styles in greyscale | <img src="docs/screenshots/sphere.png" alt="sphere"><br>`sphere`: a shaded ball bouncing over a gradient |

The logo animation step by step: a bubble is shot up and pops, its ring reveals the title, the "3D" badge springs in, the panel blinks, and from then on a glint sweeps over it every few seconds.

| | | | |
|:---:|:---:|:---:|:---:|
| <img src="docs/screenshots/logo-1-shot.png" alt="shot"> | <img src="docs/screenshots/logo-2-reveal.png" alt="reveal"> | <img src="docs/screenshots/logo-3-badge.png" alt="badge"> | <img src="docs/screenshots/logo-4-glint.png" alt="glint"> |

### The status display

Pages take turns under a strip that always shows whether the server is online and what time it is (with a blinking colon, so a frozen panel is recognisably frozen). Each page is pushed out by the next one with a slide that starts slowly and brakes at the end. When something fails, the alert page takes over and the whole panel pulses like a siren until the error clears or the button is held. The data here are made up.

| | |
|:---:|:---:|
| <img src="docs/screenshots/status-server.png" alt="server page"><br>Server: online, uptime, tunnel, last score | <img src="docs/screenshots/status-activity.png" alt="activity page"><br>Activity: submissions per hour, the current hour grey |
| <img src="docs/screenshots/status-top.png" alt="top players page"><br>Top players, which then rolls like film credits | <img src="docs/screenshots/status-top-roll.png" alt="top players rolling"><br>…with the nicknames as the game shows them |
| <img src="docs/screenshots/status-warnings.png" alt="warnings page"><br>Warnings, with how long each has stood | <img src="docs/screenshots/status-alert.png" alt="alert page"><br>An error: what, since when; the panel pulses |
| <img src="docs/screenshots/status-push.gif" alt="the push between pages"><br>The push between two pages | <img src="docs/screenshots/status-siren.gif" alt="the siren"><br>The siren |

### Greyscale on a 1-bit panel

An ST7565 pixel is either on or off. The greys come from switching pixels on in only some of the frames: each frame is ordered dithering with thresholds that shift from frame to frame, so over a cycle of 16 frames a pixel is on for its share of them, and neighbouring pixels take turns. At 200 frames per second, the eye (and the slow liquid crystal) averages the flicker into grey.

| One frame, as sent over SPI | What the eye averages it to | On the LCD |
|:---:|:---:|:---:|
| <img src="docs/screenshots/sphere-frame.png" alt="one 1-bit frame"> | <img src="docs/screenshots/sphere-gray.png" alt="the average"> | <img src="docs/screenshots/sphere.png" alt="on the LCD"> |
| <img src="docs/screenshots/logo-frame.png" alt="one 1-bit frame"> | <img src="docs/screenshots/logo-gray.png" alt="the average"> | <img src="docs/screenshots/logo.png" alt="on the LCD"> |

The `gradient` scene compares the methods: static Bayer dithering (top), static Floyd–Steinberg (middle) and temporal dithering (bottom), which is the only one that shows a smooth ramp.

<p align="center">
  <img src="docs/screenshots/gradient.png" alt="gradient: Bayer, Floyd-Steinberg, temporal dithering" width="49%">
  <img src="docs/screenshots/gradient-frame.png" alt="the same as one 1-bit frame" width="49%">
</p>

## Hardware

Developed on an OPEN-SMART 2.4" 128×64 ST7565 module (3.3 V) and a Raspberry Pi 5 with Raspberry Pi OS (Debian 13). It should work on other Pis and other ST7565 panels too; see [Other panels and wiring](#other-panels-and-wiring).

| LCD | Raspberry Pi pin | |
|---|---|---|
| VCC | 1 | 3.3 V |
| GND | 6 | |
| SDI (MOSI) | 19 | GPIO10, SPI0 MOSI |
| SCK | 23 | GPIO11, SPI0 SCLK |
| CS | 24 | GPIO8, SPI0 CE0 → `/dev/spidev0.0` |
| DC (A0, RS) | 22 | GPIO25 |
| RST | 18 | GPIO24 |
| Push button (optional) | 37 and 39 | GPIO26 and GND, for the status display |

Turn SPI on once (it loads without a reboot; `/dev/spidev0.0` appears a moment later):

```
sudo raspi-config nonint do_spi 0
```

## Install

```
git clone https://github.com/AntoninPrazsky/BS3D-LCD.git
cd BS3D-LCD
python3 -m venv .venv
.venv/bin/pip install -e .
```

Your user needs access to SPI and GPIO (the `spi` and `gpio` groups, which the default user on Raspberry Pi OS is in). If building `gpiod` or `spidev` fails, install `python3-dev`.

## Usage

```
.venv/bin/bs3d-lcd                                  # all scenes, 10 s each, logo first
.venv/bin/bs3d-lcd --scenes logo --duration 30      # just the logo
.venv/bin/bs3d-lcd --scenes logo,planet --loop      # repeat until Ctrl+C
.venv/bin/bs3d-lcd --scenes logo --keep             # leave the last frame on the panel
```

Every scene fades in from nothing and out again (`--fade`, default 0.4 s), and the first one blinks once after its fade-in (`--blink`). The logo makes its own entrance.

Scenes: `logo`, `test`, `gradient`, `sphere`, `circles`, `planet`, `bubbles`. `bs3d-lcd demo --help` lists all the options.

### Calibrating a panel

Start with the `test` scene. Its border must show on all four sides, with the small block in the top-left corner: if a side is cut off or the picture is mirrored, use `--col-offset`, `--mirror-x`, `--mirror-y` or `--rotate 2`.

```
.venv/bin/bs3d-lcd --scenes test
.venv/bin/bs3d-lcd sweep ratio          # coarse contrast first: pick the ratio...
.venv/bin/bs3d-lcd sweep --ratio 4      # ...then the fine contrast at that ratio
.venv/bin/bs3d-lcd compare gamma        # greyscale settings, labelled on the panel
```

`compare` steps one greyscale setting (`fps`, `phases` or `gamma`) through a range of values; `--values 0.5,0.65,0.8` picks your own.

Values found on the OPEN-SMART panel, all of them the defaults:

| Setting | Value | Why |
|---|---|---|
| `--ratio`, `--contrast` | 4, 0x30 | ratio 3 is far too light |
| `--gray-fps` | 200 | slower rates beat with the LCD's own refresh into rolling bars or blocky pixels; the bus manages about 380 at 4 MHz |
| `--phases` | 16 | the full 16-frame dithering cycle |
| `--gamma` | 0.65 | the LCD shows mid-tones lighter than their share of on-time |
| `--pixel-aspect` | 0.83 | the 128×64 pixels cover 43×26 mm, so circles need squashing to look round |

### The status display

```
.venv/bin/bs3d-lcd status --demo                    # the status display on made-up data
.venv/bin/bs3d-lcd status --demo --page-time 4      # pages change faster
.venv/bin/bs3d-lcd compare slide                    # push lengths and curves, labelled
.venv/bin/bs3d-lcd compare siren                    # siren depths, shapes and periods
.venv/bin/bs3d-lcd compare credits                  # speeds of the Top players roll
```

The logo plays first and is pushed out by the first page. With `--demo` the numbers change as time goes on, a warning comes and goes, and every 5 minutes an error sounds the siren for a minute.

- **The button**, between GPIO26 (pin 37) and GND (pin 39), needs no resistor: the line's pull-up holds it high. A short press (released within 0.8 s) shows the next page, during the siren too. A hold of 1.5 s switches the alarm off; while the siren sounds, a bar along the bottom fills as you hold. The error then stays on the Warnings page until it clears, and a new error sounds again. `--button none` runs without it.
- **The keyboard**, in a terminal: Enter is a short press, `a` + Enter a long hold, `e` or `w` + Enter raises or clears an error or a warning.
- **Tuning:** `--slide`, `--easing`, `--page-time`, `--siren`, `--siren-period`, `--siren-shape`, `--credits-speed`, `--short-press`, `--long-press`; `bs3d-lcd status --help` lists them.

It logs the frame rate once a minute (`--report`). On a Pi 5 it holds 200 fps with no late frames, using about 12 % of one core.

### Screenshots

```
.venv/bin/bs3d-lcd screenshots                  # into docs/screenshots
.venv/bin/bs3d-lcd screenshots --out /tmp/shots --scenes planet --gif planet
```

No hardware or SPI is needed. Each scene gets `NAME.png` (simulated LCD), `NAME-gray.png` (the averaged greyscale) and `NAME-frame.png` (one 1-bit frame); `--gif` adds animations. The status pages come as `status-*.png` with two animations, from made-up data (`--no-status` leaves them out).

### Tests

```
.venv/bin/python -m unittest discover -s tests
```

## Other panels and wiring

The wiring and panel options work on every command:

| Option | Default | |
|---|---|---|
| `--spi BUS.DEVICE` | `0.0` | `/dev/spidevBUS.DEVICE` |
| `--dc`, `--rst` | 25, 24 | BCM GPIO numbers; note that luma's own defaults are the other way round |
| `--spi-hz` | 4000000 | |
| `--gpiochip` | found by label | the chip of the 40-pin header (`pinctrl-rp1` on the Pi 5) |
| `--bias7` | 1/9 bias | some panels want 1/7 |
| `--pixel-aspect` | 0.83 | 1 for square pixels |
| `--invert` | | white on black |

## Using it as a library

```python
from luma.core.render import canvas
from bs3d_lcd.st7565 import open_display

device = open_display(port=0, device=0, dc=25, rst=24, contrast=0x30, ratio=4)
with canvas(device) as draw:
    draw.rectangle(device.bounding_box, outline="white")
    draw.text((10, 25), "Hello", fill="white")
device.fade(0.8, 0.4)     # fade out over 0.4 s
```

`bs3d_lcd.greyscale` has the dithering (`Dither`) and the greyscale canvas (`Canvas`); `bs3d_lcd.scene` has `Panel`, `Scene` and `play()`. A new scene is a function `scene(panel, **options) -> Scene` added to `bs3d_lcd.scenes.SCENES`; the ones in `bs3d_lcd/scenes/` show the patterns.

`bs3d_lcd.font` draws the pixel fonts into greyscale images. `bs3d_lcd.status` is the status display: `State` (what is known about the server), the pages, the strip, the `Director` (rotation, push, alarm, button), the `Siren` and the `Button`.

## License

The code is under the [MIT License](LICENSE). The fonts in `bs3d_lcd/assets/fonts` are subsets of the X11 [misc-fixed](https://gitlab.freedesktop.org/xorg/font/misc-misc) fonts by Markus Kuhn and others, which are in the public domain ("Share and enjoy."); `tools/subset_fonts.py` makes them. The BS3D logo (`bs3d_lcd/assets/bs3d-logo.png`, also shown in the screenshots) is part of the BS3D game and is not covered by it: all rights reserved.
