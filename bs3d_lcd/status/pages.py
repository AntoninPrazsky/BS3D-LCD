"""The status pages (#2, #5): each draws the latest ``State`` into the area under
the strip.

A page's ``render(state, t)`` returns a greyscale image of ``WIDTH`` x
``HEIGHT`` (mode "L", 255 = darkest), ``t`` seconds after the page came in.
The director draws it again ``redraw`` times a second; in between only the
dithering moves. ``duration(state, default)`` is how long it stays before
the next one pushes it out, and a page whose ``skip(state)`` is true has
nothing to say and is left out of the round.
"""

import time

from PIL import Image, ImageChops

from . import strip
from .ui import CUP_SHADES, GREY, draw_icon, fit, fmt_age, fmt_int, fmt_span, icon, page, row

WIDTH = 128
HEIGHT = 64 - strip.HEIGHT
STALE = 120         # seconds after which play statistics are drawn grey


class Page:
    name = "page"
    redraw = 2.0

    def __init__(self, ui):
        self.ui = ui

    def duration(self, state, default):
        return default

    def skip(self, state):
        return False

    def render(self, state, t):
        raise NotImplementedError


def _shade(at, now, limit=STALE):
    return 255 if at is not None and now - at <= limit else GREY


class ServerPage(Page):
    """ONLINE in large letters, the uptime, the tunnel and the last score."""

    name = "server"

    def render(self, state, t):
        ui, image, server = self.ui, page(WIDTH, HEIGHT), state.server
        if server is None:
            ui.big.draw(image, WIDTH // 2, 16, "STARTING", align="center")
            return image
        word = "ONLINE" if server.online else "OFFLINE"
        ui.big.draw(image, WIDTH // 2, 3, word, align="center")
        if server.version:
            ui.tiny.draw(image, WIDTH // 2, 19, server.version, align="center")
        uptime = fmt_span(state.now - server.since) if server.online and server.since else "--"
        row(image, ui.body, 27, "uptime", uptime)
        if server.tunnel is None:
            tunnel = "--"
        else:
            tunnel = f"{server.tunnel} links" if server.tunnel else "DOWN"
        row(image, ui.body, 37, "tunnel", tunnel)
        play = state.play
        if play and play.last_score_at:
            last = fmt_age(state.now - play.last_score_at) + " ago"
            row(image, ui.body, 47, "last score", last,
                value_fill=_shade(play.at, state.now))
        else:
            row(image, ui.body, 47, "last score", "--")
        return image


class TodayPage(Page):
    """Today's play, the Prague day: clears, unfinished attempts, players, time played."""

    name = "today"

    def skip(self, state):
        return state.play is None

    def render(self, state, t):
        ui, image, play = self.ui, page(WIDTH, HEIGHT), state.play
        shade = _shade(play.at, state.now)
        ui.bold.draw(image, 1, 1, "TODAY", fill=shade)
        ui.body.draw(image, WIDTH - 1, 1, time.strftime("%d.%m.", time.localtime(state.now)),
                     fill=shade, align="right")
        played = fmt_span(play.seconds_today) if play.seconds_today else "--"
        for i, (label, value) in enumerate((("clears", fmt_int(play.clears_today)),
                                            ("unfinished", fmt_int(play.attempts_today)),
                                            ("players", fmt_int(play.players_today)),
                                            ("new players", fmt_int(play.new_players_today)),
                                            ("time played", played))):
            row(image, ui.body, 12 + 9 * i, label, value, value_fill=shade)
        return image


class LatestPage(Page):
    """The newest clears: who, which level, the stars and the score, how long ago.

    Three of them fill the page; a title would leave room for two.
    """

    name = "latest"
    COUNT = 3
    PITCH = 18

    def skip(self, state):
        return not (state.play and state.play.latest)

    def render(self, state, t):
        ui, image, play = self.ui, page(WIDTH, HEIGHT), state.play
        shade = _shade(play.at, state.now)
        y = 2
        for clear in play.latest[:self.COUNT]:
            stars = ui.tiny.width(str(clear.stars)) + 2 + icon("star").width
            room = WIDTH - 2 - stars - 4
            name = fit((ui.body, ui.tiny), clear.player, room)
            name.draw(image, 1, y + ui.body.cap - name.cap, clear.player, fill=shade)
            x = WIDTH - 1 - stars
            x += ui.tiny.draw(image, x, y + 1, str(clear.stars), fill=shade) + 2
            draw_icon(image, x, y + 1, "star", fill=shade)
            ago = fmt_age(state.now - clear.at)
            detail = f"{clear.level}  {fmt_int(clear.score)}"
            ui.tiny.draw(image, 1, y + 10, detail, fill=shade)
            ui.tiny.draw(image, WIDTH - 1, y + 10, ago + " ago", fill=GREY, align="right")
            y += self.PITCH
        return image


class AllTimePage(Page):
    """Everything so far: players, clears, unfinished attempts, boards cleared, notes."""

    name = "all"

    def skip(self, state):
        return state.play is None

    def render(self, state, t):
        ui, image, play = self.ui, page(WIDTH, HEIGHT), state.play
        shade = _shade(play.at, state.now)
        ui.bold.draw(image, 1, 1, "ALL TIME", fill=shade)
        # The boards a visible player has cleared, of those the ceiling tables name
        boards = f"{fmt_int(play.boards_cleared)} of {fmt_int(play.boards)}" if play.boards else \
            fmt_int(play.boards_cleared)
        for i, (label, value) in enumerate((("players", fmt_int(play.players)),
                                            ("clears", fmt_int(play.clears)),
                                            ("unfinished", fmt_int(play.attempts)),
                                            ("boards", boards),
                                            ("notes", fmt_int(play.notes)))):
            row(image, ui.body, 12 + 9 * i, label, value, value_fill=shade)
        return image


class ActivityPage(Page):
    """Submissions per hour over the last 24 hours, as bars."""

    name = "activity"
    TOP, BASE = 12, 45          # the bars' top and baseline rows

    def skip(self, state):
        return not (state.play and state.play.hours)

    def render(self, state, t):
        ui, image, play = self.ui, page(WIDTH, HEIGHT), state.play
        hours = list(play.hours[-24:])
        shade = _shade(play.at, state.now)
        ui.body.draw(image, 1, 1, "LAST 24 HOURS", fill=shade)
        ui.body.draw(image, WIDTH - 1, 1, fmt_int(sum(hours)), fill=shade, align="right")

        peak = max(hours) or 1
        tall = self.BASE - self.TOP
        left = (WIDTH - (len(hours) * 5 - 1)) // 2
        hour0 = int(state.now // 3600) - (len(hours) - 1)
        for i, value in enumerate(hours):
            x = left + i * 5
            h = round(value / peak * tall)
            if value and not h:
                h = 1
            # The current hour is still filling: grey.
            fill = GREY if i == len(hours) - 1 else shade
            if h:
                image.paste(fill, (x, self.BASE - h, x + 4, self.BASE))
            local = time.localtime((hour0 + i) * 3600)
            if local.tm_hour % 6 == 0 and 4 <= x <= WIDTH - 10:
                ui.tiny.draw(image, x + 2, self.BASE + 3, f"{local.tm_hour:02d}", align="center")
        image.paste(255, (left - 1, self.BASE, left + len(hours) * 5, self.BASE + 1))
        return image


class TopPlayersPage(Page):
    """The best players, rolling upwards like the credits of a film (#5).

    This month's ten and all time's ten, each player as two centred lines:
    the nickname (a cup for the first three) and the score, levels and
    stars. The page comes in with its title at the top, holds it for
    ``hold`` s, rolls one lap at ``speed`` px/s and leaves with the title at
    the top again. After the last player a gap, then the title again: the
    list is a loop with no jump.
    """

    name = "top"
    TOP_PAD, GAP, FADE = 4, 24, 3

    def __init__(self, ui, speed=8.0, hold=1.5, fade=True):
        super().__init__(ui)
        self.speed, self.hold, self.fade = speed, hold, fade
        self.redraw = speed
        self._built = None          # (key, loop image, lap length)
        self._mask = None

    def skip(self, state):
        return not (state.play and (state.play.top_month or state.play.top_all))

    def _content(self, state):
        ui, play = self.ui, state.play
        sections = [(title, players) for title, players in
                    (("THIS MONTH", play.top_month), ("ALL TIME", play.top_all)) if players]
        rows = 1 + sum(1 + 2 * len(players) for _, players in sections)
        image = page(WIDTH, 40 + rows * 13)
        y = self.TOP_PAD
        ui.bold.draw(image, WIDTH // 2, y, "TOP PLAYERS", align="center")
        y += ui.bold.cap + 9
        for title, players in sections:
            width = ui.tiny.width(title)
            ui.tiny.draw(image, WIDTH // 2, y, title, align="center")
            line_y = y + ui.tiny.cap // 2
            image.paste(GREY, (8, line_y, WIDTH // 2 - width // 2 - 4, line_y + 1))
            image.paste(GREY, (WIDTH // 2 + width // 2 + 4, line_y, WIDTH - 8, line_y + 1))
            y += ui.tiny.cap + 6
            for player in players:
                y = self._player(image, y, player) + 5
            y += 3
        return image.crop((0, 0, WIDTH, y))

    def _player(self, image, y, player):
        """Draw one player's two lines from row ``y``; returns the row under them."""
        ui = self.ui
        if player.rank <= 3:
            lead, lead_w = "cup", icon("cup").width
        else:
            lead, lead_w = f"{player.rank}.", ui.body.width(f"{player.rank}.")
        # A long nickname of wide letters takes a narrower font.
        font = fit((ui.name, ui.bold, ui.body), player.name, WIDTH - 2 - lead_w - 4)
        name_top = y + ui.name.ascent - ui.name.cap   # room for marks on capitals
        baseline = name_top + ui.name.cap
        width = lead_w + 4 + font.width(player.name)
        x = (WIDTH - width) // 2
        if lead == "cup":
            draw_icon(image, x, baseline - icon("cup").height, "cup",
                      fill=CUP_SHADES[player.rank - 1])
        else:
            ui.body.draw(image, x, baseline - ui.body.cap, lead)
        font.draw(image, x + lead_w + 4, baseline - font.cap, player.name)

        y = baseline + ui.name.descent + 1
        stats = f"{fmt_int(player.score)}  {player.levels} lv  {player.stars}"
        width = ui.tiny.width(stats) + 2 + icon("star").width
        x = (WIDTH - width) // 2
        x += ui.tiny.draw(image, x, y, stats, fill=255) + 2
        draw_icon(image, x, y, "star")
        return y + ui.tiny.cap

    def _build(self, state):
        key = (state.play.top_month, state.play.top_all)
        if self._built is None or self._built[0] != key:
            content = self._content(state)
            if content.height <= HEIGHT:
                loop, lap = content, 0
            else:
                lap = content.height + self.GAP
                loop = page(WIDTH, lap + HEIGHT)
                loop.paste(content, (0, 0))
                loop.paste(content.crop((0, 0, WIDTH, HEIGHT)), (0, lap))
            self._built = key, loop, lap
        return self._built[1], self._built[2]

    def duration(self, state, default):
        if self.skip(state):
            return default
        _, lap = self._build(state)
        return default if not lap else self.hold + lap / self.speed + 0.5

    def offset(self, state, t):
        _, lap = self._build(state)
        return 0 if not lap else min(int(max(t - self.hold, 0) * self.speed), lap)

    def render(self, state, t):
        loop, lap = self._build(state)
        y = self.offset(state, t)
        image = loop.crop((0, y, WIDTH, y + HEIGHT))
        if lap and self.fade:
            image = ImageChops.multiply(image, self._fade_mask())
        return image

    def _fade_mask(self):
        """Full in the middle, fading over ``FADE`` rows at the top and bottom."""
        if self._mask is None:
            column = [255] * HEIGHT
            for i in range(self.FADE):
                v = round(255 * (i + 1) / (self.FADE + 1))
                column[i] = column[HEIGHT - 1 - i] = v
            self._mask = Image.new("L", (1, HEIGHT))
            self._mask.putdata(column)
            self._mask = self._mask.resize((WIDTH, HEIGHT))
        return self._mask


class BoxPage(Page):
    """The Pi itself: temperature and fan, load and memory, free space, the backup."""

    name = "box"
    GB = 1e9

    def skip(self, state):
        return state.box is None

    def render(self, state, t):
        ui, image, box = self.ui, page(WIDTH, HEIGHT), state.box
        shade = _shade(box.at, state.now, 60)
        ui.bold.draw(image, 1, 1, box.host or "PI")
        if box.uptime is not None:
            ui.body.draw(image, WIDTH - 1, 1, f"up {fmt_span(box.uptime)}", fill=shade,
                         align="right")
        cpu = "--" if box.temp is None else f"{box.temp:.0f} °C"
        if box.fan:
            cpu += f" · {fmt_int(box.fan)} rpm"
        load = "--" if box.load is None else f"{box.load:.2f}"
        if box.memory is not None:
            load += f" · mem {100 * box.memory:.0f} %"
        disk = "--" if box.disk_free is None else f"{box.disk_free / self.GB:.0f} GB free"
        card = "not mounted" if box.card_free is None else f"{box.card_free / self.GB:.0f} GB free"
        backup = "--" if box.backup_at is None else f"{fmt_age(state.now - box.backup_at)} ago"
        for i, (label, value) in enumerate((("cpu", cpu), ("load", load), ("disk", disk),
                                            ("card", card), ("backup", backup))):
            row(image, ui.body, 12 + 9 * i, label, value, value_fill=shade)
        return image


class WarningsPage(Page):
    """Each standing warning and error, with how long it has stood."""

    name = "warnings"
    LINES = 4

    def skip(self, state):
        return not state.alerts

    def render(self, state, t):
        ui, image = self.ui, page(WIDTH, HEIGHT)
        alerts = sorted(state.alerts, key=lambda a: (a.severity != "error", a.since))
        ui.bold.draw(image, 1, 1, "WARNINGS" if not state.errors else "ALERTS")
        ui.body.draw(image, WIDTH - 1, 1, str(len(alerts)), align="right")
        shown = alerts if len(alerts) <= self.LINES else alerts[:self.LINES - 1]
        y = 13
        for alert in shown:
            draw_icon(image, 1, y, "error" if alert.severity == "error" else "warning")
            title = alert.title
            age = fmt_age(state.now - alert.since)
            room = WIDTH - 11 - ui.body.width(age) - 4
            while ui.body.width(title) > room and len(title) > 1:
                title = title[:-1]
            ui.body.draw(image, 11, y, title)
            ui.body.draw(image, WIDTH - 1, y, age, align="right")
            y += 11
        if len(shown) < len(alerts):
            ui.body.draw(image, 11, y, f"+{len(alerts) - len(shown)} more", fill=GREY)
        return image


class AlertPage(Page):
    """The error that sounds the siren: what is wrong and since when (#3).

    With several, they take turns every ``turn`` s, numbered "1/2".
    """

    name = "alert"
    turn = 3.0

    def render(self, state, t):
        ui, image = self.ui, page(WIDTH, HEIGHT)
        alerts = state.alarms or state.errors
        image.paste(255, (0, 0, WIDTH, 11))
        ui.bold.draw(image, 3, 2, "ERROR", fill=0)
        if not alerts:
            return image
        index = int(t / self.turn) % len(alerts)
        alert = alerts[index]
        if len(alerts) > 1:
            ui.body.draw(image, WIDTH - 3, 2, f"{index + 1}/{len(alerts)}", fill=0, align="right")
        font = fit((ui.big, ui.name, ui.bold), alert.title, WIDTH - 4)
        top = 16 if font is ui.big else 19
        font.draw(image, WIDTH // 2, top, alert.title, align="center")
        if alert.detail:
            detail = fit((ui.body, ui.tiny), alert.detail, WIDTH - 2)
            detail.draw(image, WIDTH // 2, 34, alert.detail, align="center")
        since = time.strftime("%H:%M", time.localtime(alert.since))
        ui.tiny.draw(image, WIDTH // 2, 47,
                     f"since {since} ({fmt_age(state.now - alert.since)})", align="center")
        return image


class RecoveredPage(Page):
    """Shown once when the last error clears: what it was and how long it lasted."""

    name = "recovered"

    def __init__(self, ui, titles, lasted):
        super().__init__(ui)
        self.titles, self.lasted = titles, lasted

    def render(self, state, t):
        ui, image = self.ui, page(WIDTH, HEIGHT)
        ui.big.draw(image, WIDTH // 2, 6, "RECOVERED", align="center")
        ui.body.draw(image, WIDTH // 2, 27, f"after {fmt_span(self.lasted)}", align="center")
        text = ", ".join(self.titles)
        font = fit((ui.body, ui.tiny), text, WIDTH - 2)
        font.draw(image, WIDTH // 2, 41, text, fill=GREY, align="center")
        return image


# Every other pixel, as a checkerboard: what stays of the last picture after a stop.
CHECKER = Image.new("1", (WIDTH, 64))
CHECKER.putdata([255 if (x + y) % 2 == 0 else 0 for y in range(64) for x in range(WIDTH)])


def stopped(ui, wall, last=None, banner=True):
    """What the panel keeps showing after a clean stop (#6).

    Nothing drives the panel any more, so it is plain black and white: no
    greys, no blinking. The last picture stays, thinned out to every other
    pixel, under a STOPPED banner with the date and time; without a last
    picture, the banner alone.
    """
    when = time.strftime("%d.%m. %H:%M", time.localtime(wall))
    if last is None:
        image = page(WIDTH, 64)
        ui.big.draw(image, WIDTH // 2, 12, "STOPPED", align="center")
        ui.body.draw(image, WIDTH // 2, 34, when, align="center")
        ui.tiny.draw(image, WIDTH // 2, 50, "the status display is off", align="center")
        return image.point(lambda v: 255 if v >= 128 else 0).convert("1")

    ink = last.point(lambda v: 255 if v >= 64 else 0).convert("1")
    # Strokes one pixel wide would fall apart into dots: widen them first, so
    # every other pixel of them still reads as a letter.
    ink = ImageChops.logical_or(ink, ImageChops.offset(ink, 1, 0))
    image = ImageChops.logical_and(ink, CHECKER).convert("L")
    if banner:
        width = max(ui.big.width("STOPPED"), ui.body.width(when)) + 14
        height = 4 + ui.big.cap + 5 + ui.body.cap + 5
        x, y = (WIDTH - width) // 2, (64 - height) // 2
        image.paste(0, (x - 2, y - 2, x + width + 2, y + height + 2))
        image.paste(255, (x, y, x + width, y + height))
        image.paste(0, (x + 1, y + 1, x + width - 1, y + height - 1))
        ui.big.draw(image, WIDTH // 2, y + 4, "STOPPED", align="center")
        ui.body.draw(image, WIDTH // 2, y + 4 + ui.big.cap + 5, when, align="center")
    return image.convert("1")


def rotation(ui, credits_speed=8.0):
    """The pages that take turns, in order (#5)."""
    return [ServerPage(ui), WarningsPage(ui), TodayPage(ui), LatestPage(ui), ActivityPage(ui),
            TopPlayersPage(ui, speed=credits_speed), AllTimePage(ui), BoxPage(ui)]
