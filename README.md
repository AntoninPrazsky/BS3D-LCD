# BS3D-LCD

A 2.4" ST7565 128×64 monochrome LCD on a Raspberry Pi 5, as the front-panel display of the [BS3D](https://github.com/AntoninPrazsky/BS3D) game server (the Pi that runs [BS3D-API](https://github.com/AntoninPrazsky/BS3D-API)). It greets you with the game's animated startup logo, and is becoming the server's status display: whether the server is online, how the playing goes, and a siren when something fails ([the plan](https://github.com/AntoninPrazsky/BS3D-LCD/issues/1)).

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

Pages take turns under a strip that always shows whether the server is online and what time it is (with a blinking colon, so a frozen panel is recognisably frozen). Each page is pushed out by the next one with a slide that starts slowly and brakes at the end. When something fails, the alert page takes over and the whole panel pulses like a siren until the error clears or the button is held. When a player sends a note, the NEW NOTE page takes over and the panel knocks, two short dips every 4 s, until the button is held. The data here are made up.

| | |
|:---:|:---:|
| <img src="docs/screenshots/status-server.png" alt="server page"><br>Server: online, uptime, tunnel, last score | <img src="docs/screenshots/status-today.png" alt="today page"><br>Today: clears, unfinished, players, time played |
| <img src="docs/screenshots/status-latest.png" alt="latest scores page"><br>Latest scores: who, which level, the stars (a grey 0 unfinished), how long ago; three at a time | <img src="docs/screenshots/status-players.png" alt="latest players page"><br>Latest players: today's clears and unfinished attempts, NEW on a first day |
| <img src="docs/screenshots/status-activity.png" alt="activity page"><br>Activity: submissions per hour, the current hour grey | <img src="docs/screenshots/status-top.png" alt="top players page"><br>Top players, which then rolls like film credits |
| <img src="docs/screenshots/status-top-roll.png" alt="top players rolling"><br>…with the nicknames as the game shows them | <img src="docs/screenshots/status-all.png" alt="all time page"><br>All time: players, clears, boards cleared, notes |
| <img src="docs/screenshots/status-box.png" alt="the Pi page"><br>The Pi: temperature, fan, load, space, backup | <img src="docs/screenshots/status-warnings.png" alt="warnings page"><br>Warnings, with how long each has stood |
| <img src="docs/screenshots/status-alert.png" alt="alert page"><br>An error: what, since when; the panel pulses | <img src="docs/screenshots/status-stopped.png" alt="stopped"><br>Stopped: over the last picture, which stays |
| <img src="docs/screenshots/status-note.png" alt="new note page"><br>A new note: who sent it and when, never its text | <img src="docs/screenshots/status-note.gif" alt="the knock for a new note"><br>The knock for a new note |
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
.venv/bin/bs3d-lcd status                           # the status display of this server
.venv/bin/bs3d-lcd status --demo                    # on made-up data, with alarms now and then
.venv/bin/bs3d-lcd status --demo --page-time 4      # pages change faster
.venv/bin/bs3d-lcd compare slide                    # push lengths and curves, labelled
.venv/bin/bs3d-lcd compare siren                    # siren depths, shapes and periods
.venv/bin/bs3d-lcd compare note                     # depths and periods of the knock for a new note
.venv/bin/bs3d-lcd compare credits                  # speeds of the Top players roll
```

The logo plays first and is pushed out by the first page.

- **What it reads**, each in its own thread and never the service's database: the `bs3d-api` unit (`systemctl show`), its `GET /v1/health`, the `cloudflared` unit and its readiness, the release the `/opt/bs3d-api/current` link points to, the nightly backup's unit and timer, the service's journal (`journalctl -f`, so the user needs the `adm` or `systemd-journal` group), the Pi's temperature, throttling, fan, load, memory and free space, and optionally the same health check through Cloudflare. The play statistics come from BS3D-API's status snapshot ([BS3D-API#13](https://github.com/AntoninPrazsky/BS3D-API/issues/13)), `/run/bs3d-status/status.json`, which its `bs3d-api-status.service` rewrites every 15 s for the group `bs3d-status`: counts, today's play, the newest clears and since [BS3D-API#15](https://github.com/AntoninPrazsky/BS3D-API/issues/15) (0.1.32) the newest submissions with the unfinished attempts, the players who played last and when the newest notes came and who sent them, the Top players and the backup records, never a hash, a hidden player or a note's text. Without it the play pages are left out and the strip warns NO STATS.
- **When it alerts:** the table of conditions is in [#4](https://github.com/AntoninPrazsky/BS3D-LCD/issues/4). Anything that makes the server unreachable sounds the siren: the service down for 20 s, its health failing three checks in a row, the tunnel down for a minute, or the check through Cloudflare failing three times. So do a failed backup or copy, an error the service logs, a nearly full disk, under-voltage and over 85 °C. The rest are warnings: an old copy, statistics older than 2 minutes, refusals that point at something to update (an unknown board, a game version, the notes' cap), at someone probing, or at too many.
- **The pages:** Server, Warnings (when there are any), Today, Latest scores, Latest players, Activity, Top players, All time and the Pi. A page with nothing to say is left out. Latest scores and Latest players list up to nine rows, three at a time ([#7](https://github.com/AntoninPrazsky/BS3D-LCD/issues/7)): each three stay 4 s, the next three push up from below, and a column along the right edge shows which three are on. Latest scores lists the unfinished attempts too, with a grey 0 for their stars; from a BS3D-API before 0.1.32 it shows the newest clears alone, and Latest players is left out.
- **A new note** ([#8](https://github.com/AntoninPrazsky/BS3D-LCD/issues/8)) takes over as an error does, a step below it. The NEW NOTE page says who sent the newest note, as the admin page's Notes tab names them (a name not verified with a `?`, a hidden player only as such), how many came and when; an envelope stands in the strip, and the panel knocks: two short dips of the contrast every 4 s, which reach across the room without passing for the siren. A long hold acknowledges every note the snapshot lists. While an error sounds, the siren and the alert page come first, and one hold acknowledges both. There are no quiet hours: without a backlight, the knock shows nothing in a dark room. Notes are told apart by when they came, never by their id, which BS3D-API may give again after a note is deleted. The newest one acknowledged is kept in `/var/lib/bs3d-lcd/notes-seen`, so a restart does not knock again for it; on the first start every note already there counts as seen. A BS3D-API before 0.1.32 lists no notes, and nothing knocks.
- **Settings:** `--config PATH`, else `/etc/bs3d-lcd/config.toml`, else `~/.config/bs3d-lcd/config.toml`; [`deploy/config.example.toml`](deploy/config.example.toml) lists them all with their defaults. The public address for the check through Cloudflare goes only there.
- **`--demo`** makes the numbers change as time goes on, a warning come and go, every 5 minutes an error sound the siren for a minute, and once in each 5 minutes a note knock until it is acknowledged.

- **The button**, between GPIO26 (pin 37) and GND (pin 39), needs no resistor: the line's pull-up holds it high. A short press (released within 0.8 s) shows the next page, during the siren too. A hold of 1.5 s switches the alarm off and acknowledges the notes; while the siren sounds or a note knocks, a bar along the bottom fills as you hold. The error then stays on the Warnings page until it clears, and a new error sounds again. `--button none` runs without it.
- **The keyboard**, in a terminal: Enter is a short press, `a` + Enter a long hold; in the demo `e` or `w` + Enter raises or clears an error or a warning, and `n` + Enter sends a note.
- **Tuning:** `--slide`, `--easing`, `--page-time`, `--siren`, `--siren-period`, `--siren-shape`, `--note-depth`, `--note-period`, `--credits-speed`, `--short-press`, `--long-press`; `bs3d-lcd status --help` lists them.

It logs the frame rate once a minute (`--report`). On a Pi 5 it holds 200 fps, using about 12 % of one core; with the sources reading, about one frame a minute comes late.

### Running it as a service

```
sudo deploy/install.sh              # install or update, and (re)start the service
systemctl status bs3d-lcd
journalctl -u bs3d-lcd              # alerts as they come and go, the frame rate every 10 min
sudo systemctl stop bs3d-lcd        # before running bs3d-lcd by hand: the service has the panel
sudo deploy/uninstall.sh            # remove it; /etc/bs3d-lcd stays
```

For the play statistics, first install BS3D-API's status snapshot and let the display's user read it (BS3D-API 0.1.27 or later):

```
sudo /opt/bs3d-api/current/deploy/install-status.sh bs3d-lcd
```

`install.sh` puts the code in `/opt/bs3d-lcd` with its own venv, adds the system user `bs3d-lcd` (no home, no login; in the group `bs3d-status` when it exists) and installs [`deploy/bs3d-lcd.service`](deploy/bs3d-lcd.service), which runs the display as that user with only the `spi`, `gpio`, `video` and `systemd-journal` groups, and one folder of its own to write, `/var/lib/bs3d-lcd` (`StateDirectory=`), for the newest note acknowledged. The first install makes `/etc/bs3d-lcd/config.toml` from your `~/.config/bs3d-lcd/config.toml`, or from the example; later ones leave it alone. To update: `git pull`, then `sudo deploy/install.sh` again.

- **At boot** the logo comes up without waiting for the network, then the pages, which say STARTING until the first readings arrive.
- **A frozen panel never passes for a working one.** The render loop pats systemd's watchdog; if it stalls for 10 s, systemd restarts the service, which sets the panel up afresh. The blinking colon of the clock shows it too.
- **A clean stop** (`systemctl stop`, an update, a shutdown) leaves STOPPED with the date and time over the last picture, so a stopped display says so instead of keeping old numbers that look current. With nothing driving the panel any more there can be no greys and no blinking, so the last picture stays thinned out to every other pixel, and the banner blinks three times while the display is still stopping.

### Screenshots

```
.venv/bin/bs3d-lcd screenshots                  # into docs/screenshots
.venv/bin/bs3d-lcd screenshots --out /tmp/shots --scenes planet --gif planet
```

No hardware or SPI is needed. Each scene gets `NAME.png` (simulated LCD), `NAME-gray.png` (the averaged greyscale) and `NAME-frame.png` (one 1-bit frame); `--gif` adds animations. The status pages come as `status-*.png` with three animations, from made-up data (`--no-status` leaves them out).

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
