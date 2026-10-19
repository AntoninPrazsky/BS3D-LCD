"""The director: which page is on the panel, the push between pages, the siren
and the button (#2, #3).

``Director.frame(now)`` composes the greyscale picture and the V0 level for
the monotonic time ``now``; it touches no hardware, so tests and screenshots
drive it with a made-up clock. ``run()`` is the loop that puts its frames on
the panel at a steady 200 fps.
"""

import time

from PIL import Image

from . import strip
from ..easing import clamp01, smootherstep
from .button import LONG, SHORT, PressTracker
from .pages import AlertPage, Page, RecoveredPage
from .siren import Siren

WIDTH, HEIGHT = 128, 64
BAR = 2             # rows of the hold bar along the bottom edge


class LogoPage(Page):
    """The startup logo as a full-screen page, so it can be pushed out like any other."""

    name = "logo"
    full = True

    def __init__(self, ui, scene):
        super().__init__(ui)
        self.scene = scene
        self.redraw = 30

    def render(self, state, t):
        return self.scene.gray(t)


class Screen:
    """A page on the panel since ``start``, with its last drawing."""

    def __init__(self, page, start):
        self.page, self.start = page, start
        self.tick, self.image = None, None

    def image_at(self, state, now):
        t = now - self.start
        tick = int(t * self.page.redraw)
        if tick != self.tick:
            self.tick, self.image = tick, self.page.render(state, t)
        return self.image


class Slide:
    def __init__(self, old, new, start, full):
        self.old, self.new, self.start, self.full = old, new, start, full


class Director:
    """Rotates the pages, pushes each next one in, and gives the screen to an alarm.

    :param source: ``source(now)`` -> the latest ``State``.
    :param pages: the pages that take turns (``pages.rotation()``).
    :param page_time: how long a page stays, unless it says otherwise.
    :param slide: the push's length in s; ``easing`` its curve.
    :param logo: a scene with ``gray(t)``, played for ``logo_time`` s first.
    :param label: shown in the strip instead of the clock (the compare tools).
    """

    def __init__(self, ui, source, pages, page_time=8.0, slide=1.0, easing=smootherstep,
                 siren=None, tracker=None, logo=None, logo_time=4.5, label=None,
                 state_every=0.1):
        self.ui, self.source, self.pages = ui, source, list(pages)
        self.page_time, self.slide_time, self.easing = page_time, slide, easing
        self.siren = siren or Siren()
        self.tracker = tracker or PressTracker()
        self.logo = LogoPage(ui, logo) if logo else None
        self.logo_time = logo_time
        self.label = label
        self.alert = AlertPage(ui)
        self.state_every = state_every

        self.screen = None          # the page on the panel
        self.slide = None           # the push under way
        self.index = -1             # the rotation page shown last
        self.acked = set()          # acknowledged error occurrences
        self.alarmed = set()        # error occurrences the alert page was pushed for
        self.incident = None        # (since, titles) of the errors standing
        self.requests = []          # SHORT and LONG presses not yet handled
        self.queued = None          # a push asked for during a push: (page, index)
        self.started = None
        self._state, self._state_at = None, None
        self._strip_key, self._strip_image = None, None

    # Input

    def edge(self, kind, t):
        """A button edge: "down" or "up" at ``t`` (monotonic)."""
        if kind == "down":
            self.tracker.down(t)
        elif self.tracker.up(t) == SHORT:
            self.requests.append(SHORT)

    def press(self, kind):
        """A press from elsewhere (the keyboard in the demo): SHORT or LONG."""
        self.requests.append(kind)

    # The rotation

    def _visible(self, state):
        return [p for p in self.pages if not p.skip(state)]

    def _next_page(self, state):
        n = len(self.pages)
        for step in range(1, n + 1):
            i = (self.index + step) % n
            if not self.pages[i].skip(state):
                return i
        return 0

    def _push(self, page, state, now, index=None):
        """Push ``page`` in; during a push, after it (the last one asked for wins)."""
        if self.slide is not None:
            self.queued = (page, index)
            return
        if index is not None:
            self.index = index
        current = self.screen
        if current is not None and current.page is page:
            current.start = now             # the same page again: just its time anew
            return
        new = Screen(page, now)
        if current is None:
            self.screen = new
            return
        self.slide = Slide(current, new, now, getattr(current.page, "full", False))

    def _push_next(self, state, now):
        i = self._next_page(state)
        self._push(self.pages[i], state, now, i)

    # One frame

    def state(self, now):
        if self._state is None or now - self._state_at >= self.state_every:
            self._state, self._state_at = self.source(now), now
        return self._state

    def frame(self, now):
        """The picture (mode "L", 255 = darkest) and the V0 level at ``now``."""
        if self.started is None:
            self.started = now
            if self.logo:
                self.screen = Screen(self.logo, now)
        state = self.state(now)

        # The logo plays first, then pushes out to the first page.
        if self.screen is None:
            self._start(state, now)
        elif self.screen.page is self.logo and self.slide is None:
            t = now - self.started
            if t < self.logo_time:
                level = self.logo.scene.level(t) if self.logo.scene.level else 1.0
                return self._compose(state, now), level
            self._start(state, now)

        state = self._alarms(state, now)
        self._buttons(state, now)
        self._rotate(state, now)
        image = self._compose(state, now)
        if self.slide and now - self.slide.start >= self.slide_time:
            self.screen, self.slide = self.slide.new, None
            if self.queued:
                (page, index), self.queued = self.queued, None
                self._push(page, state, now, index)
        return image, self.siren.level(now)

    def _start(self, state, now):
        """The first page after the logo: the alert if an error stands, else the
        first of the rotation."""
        if state.alarms:
            self._push(self.alert, state, now)
        else:
            self._push_next(state, now)

    def _alarms(self, state, now):
        standing = {a.occurrence for a in state.errors}
        self.acked &= standing
        self.alarmed &= standing
        state = state.acknowledge(self.acked)

        alarms = state.alarms
        if alarms:
            self.siren.start(now)
            new = {a.occurrence for a in alarms} - self.alarmed
            if new:
                self.alarmed |= new
                self._push(self.alert, state, now)
        else:
            self.siren.stop(now)

        if state.errors:
            since = min(a.since for a in state.errors)
            titles = tuple(dict.fromkeys(
                (self.incident[1] if self.incident else ()) + tuple(a.title for a in state.errors)))
            self.incident = (since if not self.incident else min(since, self.incident[0]), titles)
        elif self.incident:
            since, titles = self.incident
            self.incident = None
            self._push(RecoveredPage(self.ui, titles, state.now - since), state, now)
        return state

    def _buttons(self, state, now):
        if self.tracker.poll(now) == LONG:
            self.requests.append(LONG)
        requests, self.requests = self.requests, []
        for kind in requests:
            if kind == LONG:
                if state.alarms:
                    self.acked |= {a.occurrence for a in state.alarms}
                    self.siren.stop(now)
                    self._push_next(state, now)
            elif kind == SHORT:
                self._push_next(state, now)

    def _rotate(self, state, now):
        if self.slide is not None:
            return
        page = self.screen.page
        alarms = state.alarms
        if page is self.alert:
            if not alarms:
                self._push_next(state, now)
            return
        if now - self.screen.start >= page.duration(state, self.page_time):
            if alarms:
                self._push(self.alert, state, now)
            else:
                self._push_next(state, now)

    # The picture

    def _strip(self, state, now):
        visible = self._visible(state)
        page = (self.slide.new if self.slide else self.screen).page
        index = visible.index(page) if page in visible else -1
        key = (int(now * 25), index, len(visible))
        if key != self._strip_key:
            self._strip_key = key
            self._strip_image = strip.render(self.ui, state, now, index, len(visible), self.label)
        return self._strip_image

    def _full(self, screen, state, now):
        """A screen as the whole panel: a full-screen page, or the strip and a page."""
        image = screen.image_at(state, now)
        if getattr(screen.page, "full", False):
            return image
        full = Image.new("L", (WIDTH, HEIGHT))
        full.paste(self._strip(state, now), (0, 0))
        full.paste(image, (0, strip.HEIGHT))
        return full

    def _compose(self, state, now):
        slide = self.slide
        if slide is None:
            image = self._full(self.screen, state, now).copy()
        else:
            u = clamp01((now - slide.start) / self.slide_time)
            x = round(WIDTH * self.easing(u))
            image = Image.new("L", (WIDTH, HEIGHT))
            if slide.full:
                image.paste(self._full(slide.old, state, now), (-x, 0))
                image.paste(self._full(slide.new, state, now), (WIDTH - x, 0))
            else:
                image.paste(self._strip(state, now), (0, 0))
                image.paste(slide.old.image_at(state, now), (-x, strip.HEIGHT))
                image.paste(slide.new.image_at(state, now), (WIDTH - x, strip.HEIGHT))

        # While an alarm sounds, a held button fills a bar along the bottom.
        held = self.tracker.held(now)
        if held is not None and self.siren.on:
            width = round(WIDTH * min(held / self.tracker.long, 1.0))
            image.paste(0, (0, HEIGHT - BAR - 1, WIDTH, HEIGHT - BAR))
            image.paste(255, (0, HEIGHT - BAR, width, HEIGHT))
            image.paste(0, (width, HEIGHT - BAR, WIDTH, HEIGHT))
        return image


def run(device, panel, director, duration=None, button=None, commands=None, report=60.0,
        fade=0.4, fade_from=0.8, log=print):
    """Put the director's frames on the panel at the panel's greyscale rate.

    ``button`` gives edges, ``commands()`` returns SHORT/LONG presses or
    callables (the demo's keyboard). Stops after ``duration`` s, or on Ctrl+C
    with a fade-out. Every ``report`` s it logs the frame rate and how many
    frames came late, which the greys show as flicker.
    """
    fps = panel.gray_fps or 1000
    start = time.monotonic()
    paced = start               # the time frame 0 was due, moved on after a stall
    n = shown = late = 0
    slowest = 0.0
    level = None
    report_at = start + report

    def show(gray, target):
        nonlocal level, n
        if target != level:
            device.set_level(target)
            level = target
        device.display(panel.dither.frame(gray, n))
        n += 1

    try:
        while duration is None or time.monotonic() - start < duration:
            t0 = time.monotonic()
            if button:
                for kind, t in button.edges():
                    director.edge(kind, t)
            for command in commands() if commands else ():
                if callable(command):
                    command(t0)
                else:
                    director.press(command)
            gray, target = director.frame(t0)
            show(gray, target)
            shown += 1
            slowest = max(slowest, time.monotonic() - t0)

            due = paced + n / fps
            now = time.monotonic()
            if now > due + 2 / fps:
                late += 1
                paced = now - n / fps
            elif now < due:
                time.sleep(due - now)
            if report and now >= report_at:
                log(f"{shown / report:.0f} fps, {late} late, slowest frame "
                    f"{slowest * 1000:.1f} ms")
                shown = late = 0
                slowest = 0.0
                report_at = now + report
    except KeyboardInterrupt:
        # Fade out while the picture keeps going, as the demo does.
        stopping = time.monotonic()
        while fade and (t := time.monotonic() - stopping) < fade:
            gray, _ = director.frame(time.monotonic())
            show(gray, fade_from + (1 - fade_from) * (1 - t / fade))
            time.sleep(1 / fps)
        raise
