"""Screenshots of the status pages, from made-up data, without the hardware.

``status-PAGE.png`` is each page under the strip as the panel shows it;
``status-push.gif`` is a push from one page to the next and
``status-siren.gif`` the alarm. The data are the demo's: made-up numbers and
made-up nicknames, at a fixed time.
"""

import os
import time

from PIL import Image

from .. import screenshots
from . import strip
from .demo import ALERTS, DemoSource
from .director import Director
from .pages import (ActivityPage, AlertPage, AllTimePage, BoxPage, LatestPlayersPage, LatestScoresPage,
                    ServerPage, TodayPage, TopPlayersPage, WarningsPage, stopped)
from .siren import Siren
from .state import Alert, State
from .ui import UI

# 20:34:15.25 on 2026-10-16, local time: the colon shows.
WALL = time.mktime((2026, 10, 16, 20, 34, 15, 0, 0, -1)) + 0.25


def duty(panel, gray):
    """What the dithered picture averages to over a whole cycle."""
    return screenshots.average([panel.dither.frame(gray, n) for n in range(panel.dither.phases)])


def demo_state(alerts=()):
    state = DemoSource(start=0.0, wall=WALL, script=False).state(0.0)
    return State(now=state.now, server=state.server, play=state.play, box=state.box,
                 alerts=tuple(alerts))


def alert(key, minutes_ago, acknowledged=False):
    severity, title, detail = ALERTS[key]
    return Alert(key, severity, title, detail, WALL - 60 * minutes_ago, acknowledged)


def screen(ui, state, page, t, index=0, count=4):
    image = Image.new("L", (128, 64))
    image.paste(strip.render(ui, state, t, index, count), (0, 0))
    image.paste(page.render(state, t), (0, strip.HEIGHT))
    return image


def shots(ui):
    """(name, greyscale) for each still."""
    calm = demo_state()
    warned = demo_state([alert("backup-old", 64)])
    failing = demo_state([alert("api-down", 3), alert("backup-old", 64)])
    top = TopPlayersPage(ui)
    latest, players = LatestScoresPage(ui), LatestPlayersPage(ui)
    return [
        ("server", screen(ui, calm, ServerPage(ui), 1.0, 0, 8)),
        ("today", screen(ui, calm, TodayPage(ui), 1.0, 1, 8)),
        ("latest", screen(ui, calm, latest, 1.0, 2, 8)),
        ("players", screen(ui, calm, players, 1.0, 3, 8)),
        ("activity", screen(ui, calm, ActivityPage(ui), 1.0, 4, 8)),
        ("top", screen(ui, calm, top, 0.0, 5, 8)),
        ("top-roll", screen(ui, calm, top, top.hold + 9.0, 5, 8)),
        ("all", screen(ui, calm, AllTimePage(ui), 1.0, 6, 8)),
        ("box", screen(ui, calm, BoxPage(ui), 1.0, 7, 8)),
        ("warnings", screen(ui, warned, WarningsPage(ui), 1.0, 1, 5)),
        ("alert", screen(ui, failing, AlertPage(ui), 1.0, -1, 5)),
        ("stopped", stopped(ui, WALL, screen(ui, calm, ServerPage(ui), 1.0, 0, 5)).convert("L")),
    ]


def frames(director, times):
    for t in times:
        yield director.frame(t)


def write(out_dir, panel, pitch=10, colors=screenshots.LCD_COLORS, gifs=True):
    """Write the stills and the animations into ``out_dir``; returns the file names."""
    os.makedirs(out_dir, exist_ok=True)
    ui = UI()
    written = []
    for name, gray in shots(ui):
        image = screenshots.palette(screenshots.lcd(duty(panel, gray), panel.aspect, pitch,
                                                    colors))
        image.save(os.path.join(out_dir, f"status-{name}.png"), optimize=True)
        written.append(f"status-{name}.png")
    if not gifs:
        return written

    fps = 25
    calm = DemoSource(start=0.0, wall=WALL, script=False)
    push = Director(ui, calm.state, [ServerPage(ui), ActivityPage(ui)], page_time=1.0)
    times = [0.6 + k / fps for k in range(round(1.6 * fps))]
    animation = [screenshots.lcd(duty(panel, gray), panel.aspect, pitch // 2, colors, level)
                 for gray, level in frames(push, times)]
    screenshots.save_gif(animation, os.path.join(out_dir, "status-push.gif"), fps)
    written.append("status-push.gif")

    failing = DemoSource(start=0.0, wall=WALL, script=False)
    failing.toggle("api-down", -180.0)
    siren = Director(ui, failing.state, [ServerPage(ui)], siren=Siren())
    # Two swings, at a lower rate to keep the file small.
    fps = 20
    times = [k / fps for k in range(round(2 * siren.siren.period * fps))]
    animation = [screenshots.lcd(duty(panel, gray), panel.aspect, pitch // 2, colors, level)
                 for gray, level in frames(siren, times)]
    screenshots.save_gif(animation, os.path.join(out_dir, "status-siren.gif"), fps)
    written.append("status-siren.gif")
    return written
