"""What the display knows about the server: one immutable snapshot (#4).

Sources replace the ``State`` as a whole; pages only read it. Times are Unix
seconds (wall clock), so pages can show the time of day and ages. A part
that is None has not been read yet.
"""

from dataclasses import dataclass, field, replace

WARNING, ERROR = "warning", "error"


@dataclass(frozen=True)
class Alert:
    """A condition that needs attention (#3, #4).

    ``key`` names the condition ("api-down"); together with ``since`` it is
    the identity of one occurrence, so an acknowledged error that clears and
    comes back is a new one.
    """

    key: str
    severity: str           # WARNING or ERROR
    title: str              # short and upper case: "API DOWN"
    detail: str = ""        # one line: "health: timeout 2 s"
    since: float = 0.0
    acknowledged: bool = False

    @property
    def occurrence(self):
        return self.key, self.since


@dataclass(frozen=True)
class Server:
    """The service and the tunnel, read from outside (#4)."""

    at: float                       # when this was read
    online: bool                    # the service is up and answers
    since: float | None = None      # up since
    version: str | None = None      # "v0.1.25"
    tunnel: int | None = None       # cloudflared's ready connections


@dataclass(frozen=True)
class Player:
    """A row of the Top players ranking (BS3D-API#11)."""

    rank: int
    name: str
    score: int
    levels: int
    stars: int


@dataclass(frozen=True)
class Play:
    """The play statistics from the status snapshot (BS3D-API#13)."""

    at: float                           # when the snapshot was written
    hours: tuple = ()                   # submissions per hour, last 24, current one last
    clears_today: int = 0
    players_today: int = 0
    last_score_at: float | None = None
    month: str = ""                     # "2026-10"
    top_month: tuple = ()               # Player rows
    top_all: tuple = ()


@dataclass(frozen=True)
class Box:
    """The Pi itself (#4, #5)."""

    at: float
    host: str = ""
    uptime: float | None = None         # seconds
    temp: float | None = None           # CPU, °C
    throttled: int | None = None        # vcgencmd get_throttled bits
    fan: int | None = None              # rpm
    load: float | None = None           # 1-minute load average
    memory: float | None = None         # share in use, 0-1
    disk_free: int | None = None        # bytes free on /
    disk_share: float | None = None     # share free on /, 0-1
    card_free: int | None = None        # bytes free on the backup card; None: not mounted
    card_share: float | None = None
    backup_at: float | None = None      # the last nightly backup that succeeded (or ran)


@dataclass(frozen=True)
class State:
    now: float
    server: Server | None = None
    play: Play | None = None
    box: Box | None = None
    alerts: tuple = field(default=())

    @property
    def errors(self):
        return tuple(a for a in self.alerts if a.severity == ERROR)

    @property
    def warnings(self):
        return tuple(a for a in self.alerts if a.severity == WARNING)

    @property
    def alarms(self):
        """The errors nobody has acknowledged: these sound the siren."""
        return tuple(a for a in self.errors if not a.acknowledged)

    def acknowledge(self, occurrences):
        """The state with the alerts whose occurrence is in ``occurrences`` marked."""
        if not occurrences:
            return self
        return replace(self, alerts=tuple(
            replace(a, acknowledged=True) if a.occurrence in occurrences else a
            for a in self.alerts))
