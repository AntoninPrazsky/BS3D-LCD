"""The sources: what the display reads about the server, from outside it (#4).

Each source runs in its own thread at its own pace, with a timeout, and
publishes into a ``Store``; nothing here ever blocks the render loop. A
source that fails publishes the failure and keeps its last good value, which
the pages then show as stale. The display never reads the service's database.
"""

import json
import os
import re
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace

from .. import __version__

# Cloudflare turns away Python's own User-Agent (403).
USER_AGENT = f"BS3D-LCD/{__version__} (status display)"
_tls = []


@dataclass(frozen=True)
class Reading:
    """What a source last told: its last good value, and how it is failing."""

    value: object = None
    at: float | None = None             # when the last good value was read
    error: str | None = None            # the last failure; None while it works
    fails: int = 0                      # failures in a row
    failing_since: float | None = None  # the first failure of this run


class Store:
    """The latest reading of every source, and the log events (#4)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._readings = {}
        self._lock = threading.Lock()
        self.events = []                # LogEvent, oldest first

    def get(self, name):
        return self._readings.get(name, Reading())

    def ok(self, name, value):
        with self._lock:
            self._readings[name] = Reading(value, self.clock())

    def fail(self, name, error):
        with self._lock:
            now = self.clock()
            old = self._readings.get(name, Reading())
            self._readings[name] = replace(old, error=error, fails=old.fails + 1,
                                           failing_since=old.failing_since or now)

    def event(self, event):
        with self._lock:
            self.events.append(event)

    def amend(self, old, new):
        """Replace a log event, once its message has come on the next line."""
        with self._lock:
            if old in self.events:
                self.events[self.events.index(old)] = new

    def recent_events(self, since):
        with self._lock:
            self.events = [e for e in self.events if e.at >= since]
            return list(self.events)


def describe(error):
    """A failure as one short line: "timeout 2 s", "HTTP 500", "refused"."""
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    if isinstance(error, (TimeoutError, socket.timeout, subprocess.TimeoutExpired)):
        return "timeout"
    if isinstance(error, ConnectionRefusedError):
        return "refused"
    if isinstance(error, OSError) and error.strerror:
        return error.strerror.lower()
    return str(error) or type(error).__name__


# The readers: each returns a value or raises.

LOCAL_TIME = re.compile(r"^\w{3} (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \S+$")


def unit(name, *props, timeout=3.0):
    """Properties of a systemd unit; timestamps as Unix seconds, empty ones None."""
    out = subprocess.run(["systemctl", "show", name, "-p", ",".join(props), "--timestamp=unix"],
                         capture_output=True, text=True, timeout=timeout, check=True).stdout
    values = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        local = LOCAL_TIME.match(value)
        if value.startswith("@") and value[1:].isdigit():
            values[key] = float(value[1:])
        elif local:
            # Timer properties ignore --timestamp: "Thu 2026-10-22 03:37:01 CEST".
            values[key] = time.mktime(time.strptime(local.group(1), "%Y-%m-%d %H:%M:%S"))
        elif value in ("", "n/a"):
            values[key] = None
        else:
            values[key] = value
    return values


def tls():
    """One TLS context for every check: loading the certificates takes the
    interpreter for a few milliseconds, which the render loop would feel."""
    if not _tls:
        _tls.append(ssl.create_default_context())
    return _tls[0]


def get_json(url, timeout=2.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = tls() if url.startswith("https:") else None
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read(64 * 1024))


def health(url, timeout=2.0):
    """BS3D-API's GET /v1/health: {status, contract, schema, boards}; it never opens
    the database. A status other than "ok" is a failure."""
    answer = get_json(url, timeout)
    if answer.get("status") != "ok":
        raise ValueError(f"status {answer.get('status')!r}")
    return answer


def ready(url, timeout=2.0):
    """cloudflared's readiness: the number of connections to Cloudflare."""
    return int(get_json(url, timeout).get("readyConnections", 0))


def release(link):
    """The running release, from the link to its folder: "v0.1.26"."""
    return os.path.basename(os.readlink(link).rstrip("/"))


def _read(path):
    with open(path) as f:
        return f.read()


def _hwmon(name, file):
    base = "/sys/class/hwmon"
    for entry in os.listdir(base):
        try:
            if _read(os.path.join(base, entry, "name")).strip() == name:
                return _read(os.path.join(base, entry, file)).strip()
        except OSError:
            continue
    return None


def _space(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize, st.f_bavail / st.f_blocks if st.f_blocks else 0.0


def box(mount, timeout=3.0):
    """The Pi: temperature, throttling, fan, load, memory, disk and backup card."""
    values = {"host": socket.gethostname()}
    values["uptime"] = float(_read("/proc/uptime").split()[0])
    values["temp"] = int(_read("/sys/class/thermal/thermal_zone0/temp")) / 1000
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                             timeout=timeout, check=True).stdout
        values["throttled"] = int(out.strip().partition("=")[2], 16)
    except (OSError, subprocess.SubprocessError, ValueError):
        values["throttled"] = None
    fan = _hwmon("pwmfan", "fan1_input")
    values["fan"] = int(fan) if fan else None
    values["load"] = float(_read("/proc/loadavg").split()[0])
    meminfo = dict(line.split(":", 1) for line in _read("/proc/meminfo").splitlines())
    total = int(meminfo["MemTotal"].split()[0])
    available = int(meminfo["MemAvailable"].split()[0])
    values["memory"] = 1 - available / total
    values["disk_free"], values["disk_share"] = _space("/")
    if os.path.ismount(mount):
        values["card_free"], values["card_share"] = _space(mount)
    else:
        values["card_free"] = values["card_share"] = None
    return values


class Poller(threading.Thread):
    """Reads one source every ``every`` s into the store, until stopped."""

    def __init__(self, store, name, read, every, stop):
        super().__init__(name=f"source-{name}", daemon=True)
        self.store, self.source, self.read, self.every, self.stop = store, name, read, every, stop

    def run(self):
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                self.store.ok(self.source, self.read())
            except Exception as e:      # a failure is a value too
                self.store.fail(self.source, describe(e))
            self.stop.wait(max(0.0, self.every - (time.monotonic() - started)))


@dataclass(frozen=True)
class LogEvent:
    """A warning or error the service logged (#4)."""

    at: float               # Unix seconds
    level: str              # "warn", "fail" or "crit"
    text: str               # "BS3D.Api.Endpoints[0]"
    detail: str = ""        # the message's first line, when it comes on the next line


PREFIX = re.compile(r"^(warn|fail|crit): (.*)$")
LEVELS = {2: "crit", 3: "fail", 4: "warn"}     # syslog priorities, once BS3D-API#13 gives them


def parse_journal(line):
    """(level, text, at) of a journal entry in JSON, level None for any other line."""
    entry = json.loads(line)
    message = entry.get("MESSAGE", "")
    if isinstance(message, list):
        message = bytes(message).decode("utf-8", "replace")
    at = int(entry.get("__REALTIME_TIMESTAMP", 0)) / 1e6
    match = PREFIX.match(message)
    if match:
        return match.group(1), match.group(2).strip(), at
    priority = int(entry.get("PRIORITY", 6))
    if priority in LEVELS:
        return LEVELS[priority], message.strip(), at
    if priority < 2:
        return "crit", message.strip(), at
    return None, message, at


class Journal(threading.Thread):
    """Follows the service's journal for logged warnings and errors.

    The service logs through the console logger, so every line arrives at
    priority 6 and the level is the line's prefix ("fail: ..."); its message
    is the next line. It starts ``window`` s back, so events from just before
    the display started still show.
    """

    def __init__(self, store, unit_name, window, stop):
        super().__init__(name="source-journal", daemon=True)
        self.store, self.unit, self.window, self.stop = store, unit_name, window, stop
        self.process = None

    def run(self):
        while not self.stop.is_set():
            try:
                self.follow()
            except Exception as e:
                self.store.fail("journal", describe(e))
            self.stop.wait(5.0)

    def follow(self):
        command = ["journalctl", "-f", "-o", "json", "-u", self.unit,
                   "--since", f"-{int(self.window)}s"]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
        self.store.ok("journal", True)
        last = None
        for line in self.process.stdout:
            if self.stop.is_set():
                break
            level, text, at = parse_journal(line)
            if level:
                last = LogEvent(at, level, text)
                self.store.event(last)
            elif last and text[:1].isspace() and at - last.at < 1.0 and not last.detail:
                # The message under a "fail: Category[0]" line.
                detailed = replace(last, detail=text.strip())
                self.store.amend(last, detailed)
                last = detailed
        code = self.process.wait()
        # Killed by a signal: most likely the display is stopping with it. It
        # starts again in a moment if not; only an exit of its own is a failure.
        if not self.stop.is_set() and code >= 0:
            self.store.fail("journal", f"journalctl ended ({code})")

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


def start(config, store=None, stop=None):
    """Start every source; returns the store, the stop event and the threads."""
    store = store or Store()
    stop = stop or threading.Event()
    service_props = ("ActiveState", "SubState", "NRestarts", "ActiveEnterTimestamp")
    threads = [
        Poller(store, "service", lambda: unit(config.service, *service_props), 5.0, stop),
        Poller(store, "health", lambda: health(config.health), 10.0, stop),
        Poller(store, "tunnel", lambda: unit(config.tunnel, "ActiveState", "SubState"),
               10.0, stop),
        Poller(store, "ready", lambda: ready(config.ready), 10.0, stop),
        Poller(store, "release", lambda: release(config.release), 60.0, stop),
        Poller(store, "backup", lambda: unit(config.backup, "Result", "ExecMainStatus",
                                             "ExecMainExitTimestamp"), 60.0, stop),
        Poller(store, "backup-timer", lambda: unit(f"{config.backup}.timer", "LastTriggerUSec"),
               60.0, stop),
        Poller(store, "box", lambda: box(config.backup_mount), 10.0, stop),
        Journal(store, config.service, config.log_window * 60, stop),
    ]
    if config.public_health:
        tls()                       # now, before the render loop runs
        threads.append(Poller(store, "public", lambda: health(config.public_health, 5.0),
                              60.0, stop))
    for thread in threads:
        thread.start()
    return store, stop, threads


# How often each source reads, for telling a source that hangs.
EVERY = {"service": 5.0, "health": 10.0, "tunnel": 10.0, "ready": 10.0, "release": 60.0,
         "backup": 60.0, "backup-timer": 60.0, "box": 10.0, "public": 60.0}
