"""Made-up server data, for building and tuning the pages without the server (#2).

The numbers change as time goes on, and a script makes things go wrong now
and then: a warning, and an error that sounds the siren until it is
acknowledged or clears by itself. ``toggle()`` raises and clears them by
hand. All names are made up.
"""

import math
import random
import time

from .state import ERROR, WARNING, Alert, Box, Play, Player, Server, State

NAMES = ("Kateřina", "Bublinka", "Jiří", "Šárka_7", "Ondra-K", "Łukasz", "Žaneta",
         "Ægir", "Tomáš", "Mia", "Ľubo", "Zdeněk", "Øyvind", "Bára", "Kuba 77", "Eliška",
         "Jürgen", "Radek", "Veronika", "Nikol")

# The scripted trouble, in seconds within each cycle.
CYCLE = 300.0
WARNING_AT, WARNING_FOR = 50.0, 120.0
ERROR_AT, ERROR_FOR = 110.0, 60.0

ALERTS = {
    "backup-old": (WARNING, "BACKUP OLD", "last copy 27h ago"),
    "api-down": (ERROR, "API DOWN", "health: timeout 2 s"),
}


def players(rng, count, top, levels):
    names = rng.sample(NAMES, count)
    scores = sorted((rng.randint(top // 8, top) for _ in range(count)), reverse=True)
    return tuple(Player(i + 1, name, score, max(1, levels * score // top),
                        max(3, 3 * levels * score // top - rng.randint(0, 9)))
                 for i, (name, score) in enumerate(zip(names, scores)))


class DemoSource:
    """``state(now)`` for a monotonic ``now``.

    :param wall: the wall-clock time at ``start`` (default: the real one).
    :param script: make the scripted warning and error happen.
    :param seed: the made-up numbers; the same seed gives the same ones.
    """

    def __init__(self, start=None, wall=None, script=True, seed=7, top=10):
        self.start = time.monotonic() if start is None else start
        self.wall0 = time.time() if wall is None else wall
        self.script = script
        rng = random.Random(seed)
        self.top_month = players(rng, top, 600_000, 24)
        self.top_all = players(rng, top, 1_900_000, 61)
        self.base_hours = [max(0, round(18 + 14 * math.sin((h - 15) / 24 * 2 * math.pi)
                                        + rng.uniform(-6, 6))) for h in range(24)]
        self.manual = {}            # key -> (on, since) set by toggle()

    def wall(self, now):
        return self.wall0 + (now - self.start)

    def toggle(self, key, now):
        """Raise the alert ``key`` (a key of ``ALERTS``), or clear it."""
        on = self._scripted(key, now) if key not in self.manual else self.manual[key][0]
        self.manual[key] = (not on, self.wall(now))

    def _scripted(self, key, now):
        if not self.script:
            return False
        t = (now - self.start) % CYCLE
        if key == "backup-old":
            return WARNING_AT <= t < WARNING_AT + WARNING_FOR
        if key == "api-down":
            return ERROR_AT <= t < ERROR_AT + ERROR_FOR
        return False

    def _since(self, key, now):
        if key in self.manual:
            return self.manual[key][1]
        t = (now - self.start) % CYCLE
        at = WARNING_AT if key == "backup-old" else ERROR_AT
        return self.wall(now) - (t - at)

    def alerts(self, now):
        out = []
        for key, (severity, title, detail) in ALERTS.items():
            on = self.manual[key][0] if key in self.manual else self._scripted(key, now)
            if on:
                out.append(Alert(key, severity, title, detail, round(self._since(key, now))))
        return tuple(out)

    def state(self, now):
        wall = self.wall(now)
        alerts = self.alerts(now)
        down = any(a.key == "api-down" for a in alerts)
        server = Server(at=wall, online=not down, since=self.wall0 - 2 * 86400 - 4 * 3600,
                        version="v0.1.25", tunnel=4)

        # Each hour's count, the current one filling up as the hour goes on.
        hour = int(wall // 3600)
        hours = tuple(self.base_hours[(hour - 23 + i) % 24] for i in range(24))
        part = (wall % 3600) / 3600
        hours = hours[:-1] + (round(hours[-1] * part),)
        last = wall - (37 + 23 * math.sin(wall / 97) ** 2)
        play = Play(at=wall - (wall % 15), hours=hours, clears_today=sum(hours) // 3,
                    players_today=11, last_score_at=last,
                    month=time.strftime("%Y-%m", time.localtime(wall)),
                    top_month=self.top_month, top_all=self.top_all)
        box = Box(at=wall - (wall % 10), host="BS3DServer", uptime=wall - server.since + 600,
                  temp=48 + 3 * math.sin(wall / 300), throttled=0, fan=2860, load=0.42,
                  memory=0.31, disk_free=443_800_000_000, disk_share=0.88,
                  card_free=125_500_000_000, card_share=0.99, backup_at=wall - 11 * 3600)
        return State(now=wall, server=server, play=play, box=box, alerts=alerts)
