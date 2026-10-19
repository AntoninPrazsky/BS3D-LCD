"""Command line: play scenes, the server status display, calibrate the panel,
render screenshots."""

import argparse
import queue
import sys
import threading
from datetime import datetime

from . import __doc__ as package_doc, scenes
from .easing import EASINGS
from .greyscale import Dither
from .scene import Panel, run_scenes

COMMANDS = ("demo", "status", "sweep", "compare", "screenshots")
COMPARE = ("fps", "phases", "gamma", "slide", "siren", "credits")


def int_auto(value):
    return int(value, 0)


def spi_address(value):
    try:
        port, device = (int(part) for part in value.split("."))
    except ValueError:
        raise argparse.ArgumentTypeError("use BUS.DEVICE, e.g. 0.0 for /dev/spidev0.0")
    return port, device


def button_line(value):
    if value.lower() == "none":
        return None
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a BCM GPIO number, or none")


def scene_list(value):
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in scenes.SCENES]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"scenes are {', '.join(scenes.SCENES)}")
    return names


def parsers():
    hardware = argparse.ArgumentParser(add_help=False)
    g = hardware.add_argument_group("wiring and panel")
    g.add_argument("--spi", type=spi_address, default=(0, 0), metavar="BUS.DEVICE",
                   help="SPI bus and chip select: /dev/spidevBUS.DEVICE (default 0.0)")
    g.add_argument("--dc", type=int, default=25, metavar="GPIO",
                   help="BCM GPIO of the DC (A0, RS) line (default 25)")
    g.add_argument("--rst", type=int, default=24, metavar="GPIO",
                   help="BCM GPIO of the RST line (default 24)")
    g.add_argument("--gpiochip", metavar="PATH",
                   help="gpiochip of the header GPIOs (default: found by its label)")
    g.add_argument("--spi-hz", type=int_auto, default=4_000_000,
                   help="SPI clock (default 4 MHz; 0.5/1/2/4/8 MHz are safe values)")
    g.add_argument("--contrast", type=int_auto, default=0x30,
                   help="electronic volume 0x00-0x3F (default 0x30)")
    g.add_argument("--ratio", type=int, default=4, choices=range(8),
                   help="V0 resistor ratio 0-7, the coarse contrast (default 4)")
    g.add_argument("--bias7", action="store_true", help="LCD bias 1/7 instead of 1/9")
    g.add_argument("--rotate", type=int, default=0, choices=(0, 2),
                   help="2 = upside down (default 0)")
    g.add_argument("--mirror-x", action="store_true",
                   help="reverse SEG direction if the picture is mirrored left-right")
    g.add_argument("--mirror-y", action="store_true",
                   help="flip COM direction if the picture is mirrored top-bottom")
    g.add_argument("--col-offset", type=int, default=None,
                   help="first visible RAM column, if the border is cut off left or "
                        "right (default 0, or 4 with --mirror-x)")
    g.add_argument("--invert", action="store_true", help="white on black")

    greyscale = argparse.ArgumentParser(add_help=False)
    g = greyscale.add_argument_group("greyscale")
    g.add_argument("--pixel-aspect", type=float, default=0.83, metavar="W/H",
                   help="pixel width / pixel height, so circles come out round "
                        "(default 0.83 for the OPEN-SMART 2.4\" panel; 1 = square)")
    g.add_argument("--gray-fps", type=int, default=200,
                   help="frame rate of the dithered scenes; slower ones beat with the "
                        "LCD's own refresh into rolling bars (default 200, 0 = as fast as "
                        "the SPI bus allows)")
    g.add_argument("--phases", type=int, default=16, choices=Dither.PHASES,
                   help="frames per dithering cycle: fewer shimmer less but show more "
                        "dot pattern; 1 = static (default 16)")
    g.add_argument("--gamma", type=float, default=0.65,
                   help="greyscale gamma; below 1 darkens the mid-tones, which the LCD "
                        "shows too light (default 0.65)")

    show = argparse.ArgumentParser(add_help=False)
    g = show.add_argument_group("scenes")
    g.add_argument("--scenes", type=scene_list, default=list(scenes.SCENES),
                   help=f"comma-separated scenes in order (default "
                        f"{','.join(scenes.SCENES)})")
    g.add_argument("--duration", type=float, default=10.0,
                   help="length of each scene in s (default 10)")
    g.add_argument("--blink", type=float, default=1.1, metavar="LEVEL",
                   help="after the first scene's fade-in (and in the logo), pulse to "
                        "LEVEL and back (default 1.1; 1 = off)")

    p = argparse.ArgumentParser(
        prog="bs3d-lcd", description=package_doc.split("\n\n")[0],
        epilog="Without a command, runs demo. See COMMAND --help for its options.")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    d = sub.add_parser("demo", parents=[hardware, greyscale, show],
                       help="play the scenes on the panel (the default)")
    d.add_argument("--fps", type=int, default=25,
                   help="frame rate of the test scene (default 25)")
    d.add_argument("--fade", type=float, default=0.4, metavar="SECONDS",
                   help="fade each scene in from nothing and out again (default 0.4; "
                        "0 = off)")
    d.add_argument("--fade-from", type=float, default=0.8, metavar="LEVEL",
                   help="level the fade starts from and ends at, as a fraction of the "
                        "normal V0 (default 0.8; raise it if the fade lags at the start)")
    d.add_argument("--keep", action="store_true",
                   help="leave the last frame on the display on exit")
    d.add_argument("--loop", action="store_true", help="repeat the scenes until Ctrl+C")

    st = sub.add_parser("status", parents=[hardware, greyscale],
                        help="the BS3D server's status display (for now with made-up data: "
                             "--demo)")
    st.add_argument("--demo", action="store_true",
                    help="made-up data that change, with a warning and an error now and then; "
                         "type Enter for a short press, a + Enter for a long hold, e or w + "
                         "Enter to raise or clear an error or a warning")
    g = st.add_argument_group("pages")
    g.add_argument("--page-time", type=float, default=8.0, metavar="SECONDS",
                   help="how long a page stays (default 8)")
    g.add_argument("--slide", type=float, default=1.0, metavar="SECONDS",
                   help="length of the push from page to page (default 1.0)")
    g.add_argument("--easing", default="smootherstep", choices=tuple(EASINGS),
                   help="the push's curve (default smootherstep)")
    g.add_argument("--credits-speed", type=float, default=8.0, metavar="PX/S",
                   help="speed of the Top players roll; faster blurs (default 8)")
    g.add_argument("--no-logo", action="store_true", help="start without the logo")
    g = st.add_argument_group("alarm")
    g.add_argument("--siren", type=float, default=0.15, metavar="DEPTH",
                   help="the level swings between 1 - DEPTH and 1 + DEPTH (default 0.15)")
    g.add_argument("--siren-period", type=float, default=1.5, metavar="SECONDS",
                   help="one swing of the siren (default 1.5)")
    g.add_argument("--siren-shape", default="siren", choices=("siren", "sine"),
                   help="siren: quick rise, slow fall (default); sine: even")
    g.add_argument("--button", type=button_line, default=26, metavar="GPIO",
                   help="BCM GPIO of the push button to GND (default 26, pin 37; none = "
                        "no button)")
    g.add_argument("--short-press", type=float, default=0.8, metavar="SECONDS",
                   help="a release within this is a short press: the next page (default 0.8)")
    g.add_argument("--long-press", type=float, default=1.5, metavar="SECONDS",
                   help="a hold this long switches the alarm off (default 1.5)")
    st.add_argument("--report", type=float, default=60.0, metavar="SECONDS",
                    help="log the frame rate this often (default 60; 0 = never)")

    s = sub.add_parser("sweep", parents=[hardware, greyscale],
                       help="step through the contrast or ratio values to find the best")
    s.add_argument("what", nargs="?", default="contrast", choices=("contrast", "ratio"),
                   help="contrast (fine, default) or ratio (coarse; try it first)")
    s.add_argument("--step", type=int, default=4, help="contrast step (default 4)")
    s.add_argument("--hold", type=float, default=1.5, help="seconds per step (default 1.5)")

    c = sub.add_parser("compare", parents=[hardware, greyscale],
                       help="step one setting through a range of values, labelled on the "
                            "display")
    c.add_argument("what", choices=COMPARE,
                   help="fps, phases, gamma: the greyscale; slide: the push between pages; "
                        "siren: the alarm; credits: the speed of the Top players roll")
    c.add_argument("--hold", type=float, default=None,
                   help="seconds per value (default 6; slide: three pushes; credits: 15)")
    c.add_argument("--values", type=lambda v: [float(x) for x in v.split(",")],
                   metavar="A,B,...", help="values instead of the built-in ones (slide: "
                                           "lengths; siren: depths; credits: speeds)")

    r = sub.add_parser("screenshots", parents=[greyscale, show],
                       help="render PNG screenshots of the scenes; no hardware needed")
    r.add_argument("--out", default="docs/screenshots", metavar="DIR",
                   help="output folder (default docs/screenshots)")
    r.add_argument("--pitch", type=int, default=10, metavar="PX",
                   help="screenshot pixels per panel pixel across (default 10)")
    r.add_argument("--gif", type=lambda v: scene_list(v) if v else [], default=["logo"],
                   metavar="SCENES", help="scenes to animate as well, at half the pitch "
                                          "(default logo; \"\" = none)")
    r.add_argument("--gif-length", type=float, default=4.6, metavar="SECONDS",
                   help="length of the animations (default 4.6)")
    r.add_argument("--status", action=argparse.BooleanOptionalAction, default=True,
                   help="also the status pages, a push and the siren, from made-up data "
                        "(default yes)")
    return p


def open_device(args):
    from .st7565 import open_display

    port, device = args.spi
    if not 0 <= args.contrast <= 0x3F:
        raise SystemExit(f"--contrast must be 0x00-0x3F, got {args.contrast:#04x}")
    lcd = open_display(port, device, dc=args.dc, rst=args.rst, spi_hz=args.spi_hz,
                       gpiochip=args.gpiochip, rotate=args.rotate, contrast=args.contrast,
                       ratio=args.ratio, bias9=not args.bias7, mirror_x=args.mirror_x,
                       mirror_y=args.mirror_y, col_offset=args.col_offset,
                       invert=args.invert)
    lcd.persist = getattr(args, "keep", False)
    print(f"ST7565 on /dev/spidev{port}.{device} @ {args.spi_hz / 1e6:g} MHz, "
          f"DC=GPIO{args.dc}, RST=GPIO{args.rst}, contrast {args.contrast:#04x}, "
          f"ratio {args.ratio}, rotate {args.rotate}, column offset {lcd.col_offset}",
          flush=True)
    return lcd


def keyboard(source):
    """The demo's keyboard: lines typed on stdin, as presses and alarms."""
    from .status.button import LONG, SHORT

    lines = queue.SimpleQueue()

    def read():
        for line in sys.stdin:
            lines.put(line.strip().lower())
    threading.Thread(target=read, name="keyboard", daemon=True).start()

    def commands():
        out = []
        while True:
            try:
                line = lines.get_nowait()
            except queue.Empty:
                return out
            if line == "":
                out.append(SHORT)
            elif line == "a":
                out.append(LONG)
            elif line in ("e", "w"):
                key = "api-down" if line == "e" else "backup-old"
                out.append(lambda now, key=key: source.toggle(key, now))
    return commands


def run_status(lcd, panel, args):
    from .easing import EASINGS
    from .status.button import Button, PressTracker
    from .status.demo import DemoSource
    from .status.director import Director, run
    from .status.pages import rotation
    from .status.siren import Siren
    from .status.ui import UI

    ui = UI()
    source = DemoSource()
    logo = None if args.no_logo else scenes.SCENES["logo"](panel)
    director = Director(ui, source.state, rotation(ui, args.credits_speed),
                        page_time=args.page_time, slide=args.slide,
                        easing=EASINGS[args.easing],
                        siren=Siren(1 - args.siren, 1 + args.siren, args.siren_period,
                                    args.siren_shape),
                        tracker=PressTracker(args.short_press, args.long_press), logo=logo)
    button = None
    if args.button is not None:
        try:
            button = Button(args.button, args.gpiochip)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"Button on GPIO{args.button}: a short press shows the next page, a hold of "
              f"{args.long_press:g} s switches the alarm off.", flush=True)
    commands = keyboard(source) if sys.stdin.isatty() else None
    if commands:
        print("Keys (+ Enter): Enter = short press, a = long hold, e = error on/off, "
              "w = warning on/off.", flush=True)
    try:
        run(lcd, panel, director, button=button, commands=commands, report=args.report,
            log=lambda line: print(line, flush=True))
    finally:
        if button:
            button.close()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        argv.insert(0, "demo")
    args = parsers().parse_args(argv)
    panel = Panel(aspect=args.pixel_aspect, phases=args.phases, gamma=args.gamma,
                  gray_fps=args.gray_fps)

    if args.command == "screenshots":
        from . import screenshots

        # A fixed time, so the test screen doesn't change with every run.
        written = screenshots.write(args.out, args.scenes, panel, args.pitch,
                                    gifs=args.gif, gif_length=args.gif_length,
                                    duration=args.duration, blink=args.blink,
                                    now=lambda: datetime(2026, 10, 15, 12, 34, 56))
        if args.status:
            from .status import shots
            written += shots.write(args.out, panel, args.pitch)
        print(f"{len(written)} screenshots written to {args.out}/")
        return 0

    if args.command == "status" and not args.demo:
        print("The server's sources are not there yet (BS3D-LCD#4): run it with --demo.",
              file=sys.stderr)
        return 2
    try:
        lcd = open_device(args)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    try:
        if args.command == "status":
            return run_status(lcd, panel, args)
        if args.command == "sweep":
            from .calibrate import run_sweep
            run_sweep(lcd, panel, args.what, args.contrast, args.ratio, args.step, args.hold)
        elif args.command == "compare" and args.what in ("slide", "siren", "credits"):
            from .status.compare import run_compare
            run_compare(lcd, panel, args.what, args.values, args.hold)
        elif args.command == "compare":
            from .calibrate import run_compare
            run_compare(lcd, panel, args.what, args.values, args.hold or 6.0)
        else:
            run_scenes(lcd, scenes.build(args.scenes, panel, duration=args.duration,
                                         fps=args.fps, blink=args.blink),
                       args.duration, args.fade, args.fade_from, args.blink, args.keep,
                       args.loop)
    except KeyboardInterrupt:
        print("Interrupted.")
    return 0
