"""Tuning on the panel: the push, the siren and the Top players roll, each setting
in turn, labelled in the strip (#2, #3, #5)."""

from ..easing import EASINGS
from .demo import DemoSource
from .director import Director, run
from .pages import ActivityPage, ServerPage, TopPlayersPage
from .siren import Siren
from .ui import UI

# The first of each is the default, picked by the owner on the panel (2026-10-19).
# (easing, length in s)
SLIDES = (("smootherstep", 1.0), ("smootherstep", 0.7), ("smootherstep", 1.3),
          ("sine", 1.0), ("cubic", 1.0), ("linear", 1.0))
# (shape, depth, period in s): the level swings between 1 - depth and 1 + depth.
SIRENS = (("siren", 0.15, 1.5), ("siren", 0.10, 1.5), ("siren", 0.20, 1.5),
          ("sine", 0.15, 1.5), ("siren", 0.15, 1.0), ("siren", 0.15, 2.0))
CREDITS = (8, 6, 10, 12)        # px/s; faster ones blur on the slow liquid crystal

HOLD = {"slide": None, "siren": 6.0, "credits": 15.0}
PAGE_TIME = 2.0                 # between the pushes of compare slide


def settings(what, values=None):
    """(label, director factory, seconds) for each setting to show."""
    ui = UI()
    out = []
    if what == "slide":
        slides = SLIDES if not values else [("smootherstep", v) for v in values]
        for easing, length in slides:
            def make(label, easing=easing, length=length):
                source = DemoSource(script=False)
                pages = [ServerPage(ui), ActivityPage(ui)]
                return Director(ui, source.state, pages, page_time=PAGE_TIME, slide=length,
                                easing=EASINGS[easing], label=label)
            out.append((f"{easing} {length:g}s", make, 3 * (PAGE_TIME + length)))
    elif what == "siren":
        sirens = SIRENS if not values else [("siren", v, 1.5) for v in values]
        for shape, depth, period in sirens:
            def make(label, shape=shape, depth=depth, period=period):
                source = DemoSource(script=False)
                source.toggle("api-down", source.start - 180)
                siren = Siren(1 - depth, 1 + depth, period, shape)
                return Director(ui, source.state, [ServerPage(ui)], siren=siren, label=label)
            out.append((f"{shape} {depth:g} {period:g}s", make, None))
    elif what == "credits":
        for speed in values or CREDITS:
            def make(label, speed=speed):
                source = DemoSource(script=False)
                return Director(ui, source.state, [TopPlayersPage(ui, speed=speed)],
                                label=label)
            out.append((f"{speed:g} px/s", make, None))
    else:
        raise ValueError(f"nothing to compare called {what!r}")
    return out


def run_compare(device, panel, what, values=None, hold=None, log=print):
    """Show each setting of ``what`` (slide, siren or credits) for a while, labelled."""
    chosen = settings(what, values)
    for i, (label, make, seconds) in enumerate(chosen, 1):
        label = f"{label}  {i}/{len(chosen)}"
        log(label)
        director = make(label)
        run(device, panel, director, duration=hold or seconds or HOLD[what], report=0,
            fade=0)
