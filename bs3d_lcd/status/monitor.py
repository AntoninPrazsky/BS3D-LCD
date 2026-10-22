"""From the sources' readings to a ``State``: the server, the Pi and the alerts (#4).

Each condition has a severity and a hold: how long it must stand before it
alerts, so that a deploy's restart or one slow answer does not sound the
siren. Everything that makes the server unreachable is an error (the owner,
2026-10-16: "certainly if the server is offline or not responding"); what
needs attention but not right now is a warning. An alert keeps the time its
condition began, which is also its identity for acknowledging (#3).
"""

import time

from .sources import EVERY
from .state import ERROR, WARNING, Alert, Box, Server, State
from .ui import fmt_age, fmt_span

GB = 1e9
OFFLINE = ("service-down", "health", "tunnel", "public")
UNDER_VOLTAGE, CAPPED, THROTTLED, SOFT_LIMIT = 1 << 0, 1 << 1, 1 << 2, 1 << 3
UNDER_VOLTAGE_SEEN = 1 << 16


class Monitor:
    """``monitor(now)`` -> the ``State`` from the store's latest readings.

    ``now`` is the director's monotonic time and is not used: ages and holds
    are measured on the wall ``clock``.
    """

    def __init__(self, config, store, clock=time.time, log=None):
        self.config, self.store, self.clock, self.log = config, store, clock, log
        self.logged = {}            # the alerts standing at the last state, for the log
        self.started = clock()
        self.began = {}             # condition key -> when it began (Unix seconds)
        self.restarts = []          # when automatic restarts were seen
        self.restarts_count = None

    def __call__(self, now=None):
        return self.state()

    # Helpers

    def held(self, key, on, hold, now, began=None):
        """When the condition began, once it has stood ``hold`` s; else None."""
        if not on:
            self.began.pop(key, None)
            return None
        began = self.began.setdefault(key, now if began is None else began)
        return began if now - began >= hold else None

    def fresh(self, name, now):
        """The source's value, if it is recent; else None."""
        reading = self.store.get(name)
        if reading.value is None or reading.at is None:
            return None
        return reading.value if now - reading.at <= 3 * EVERY.get(name, 10.0) + 10 else None

    # The state

    def state(self):
        now = self.clock()
        c = self.config
        alerts = []

        def alert(key, severity, title, detail, since):
            alerts.append(Alert(key, severity, title, detail, float(round(since))))

        # The service.
        service = self.fresh("service", now)
        active = service is not None and service["ActiveState"] in ("active", "reloading")
        down = self.held("service-down", service is not None and not active, c.service_hold, now)
        if down:
            alert("service-down", ERROR, "API DOWN",
                  f"{c.service}: {service['ActiveState']} ({service['SubState']})", down)
        self.count_restarts(service, now)
        recent = [t for t in self.restarts if now - t < 3600]
        if self.restarts and now - self.restarts[-1] < 86400:
            severity = ERROR if len(recent) >= 3 else WARNING
            last = time.strftime("%H:%M", time.localtime(self.restarts[-1]))
            alert("restarts", severity, "API RESTARTED",
                  f"{len(self.restarts)}x, last at {last}", self.restarts[0])

        # It answers, with its ceilings. A service systemd says is down will be
        # API DOWN once its hold is over; NO ANSWER is for one that runs but is silent.
        health = self.store.get("health")
        if health.fails >= c.health_fails and (service is None or active):
            alert("health", ERROR, "NO ANSWER", f"health: {health.error}", health.failing_since)
        answer = self.fresh("health", now)
        no_boards = bool(answer) and health.fails == 0 and answer.get("boards") == 0
        began = self.held("no-boards", no_boards, 15.0, now)
        if began:
            alert("no-boards", ERROR, "NO BOARDS", "no ceiling table: every score refused",
                  began)

        # The tunnel.
        tunnel = self.fresh("tunnel", now)
        connections = self.fresh("ready", now)
        unit_down = tunnel is not None and tunnel["ActiveState"] != "active"
        began = self.held("tunnel", unit_down or connections == 0, c.tunnel_hold, now)
        if began:
            detail = f"{c.tunnel}: {tunnel['ActiveState']}" if unit_down else "0 connections"
            alert("tunnel", ERROR, "TUNNEL DOWN", detail, began)

        # And the world reaches it, through Cloudflare.
        public = self.store.get("public")
        if c.public_health and public.fails >= c.public_fails and not alerts_with(alerts, OFFLINE):
            alert("public", ERROR, "UNREACHABLE", f"public health: {public.error}",
                  public.failing_since)

        self.log_alerts(alert, now)
        backup_at = self.backup_alerts(alert, now)
        box = self.fresh("box", now)
        if box:
            self.box_alerts(alert, box, now)
        self.source_alerts(alert, now, unit_down)

        server = None
        if service is not None or health.at or health.fails:
            server = Server(at=now, online=not alerts_with(alerts, OFFLINE),
                            since=service.get("ActiveEnterTimestamp") if active else None,
                            version=self.fresh("release", now), tunnel=connections)
        box_state = None
        if box:
            box_state = Box(at=self.store.get("box").at, backup_at=backup_at, **box)
        alerts.sort(key=lambda a: (a.severity != ERROR, a.since))
        self.log_changes(alerts, now)
        return State(now=now, server=server, box=box_state, alerts=tuple(alerts))

    def log_changes(self, alerts, now):
        """Each alert into the log as it comes and goes: the journal keeps the history."""
        current = {a.occurrence: a for a in alerts}
        if self.log:
            for occurrence, a in current.items():
                if occurrence not in self.logged:
                    self.log(f"{a.severity}: {a.title}, {a.detail}")
            for occurrence, a in self.logged.items():
                if occurrence not in current:
                    self.log(f"cleared: {a.title}, after {fmt_span(now - a.since)}")
        self.logged = current

    def count_restarts(self, service, now):
        """Automatic restarts: systemd counts them in NRestarts."""
        if service is None or service.get("NRestarts") is None:
            return
        count = int(service["NRestarts"])
        if self.restarts_count is not None and count > self.restarts_count:
            self.restarts += [now] * (count - self.restarts_count)
        self.restarts_count = count
        self.restarts = [t for t in self.restarts if now - t < 86400]

    def log_alerts(self, alert, now):
        """What the service logged: an error stands until a quiet window has passed."""
        window = self.config.log_window * 60
        events = self.store.recent_events(now - window)
        for key, levels, severity, title in (
                ("log-error", ("fail", "crit"), ERROR, "API ERROR"),
                ("log-warning", ("warn",), WARNING, "API WARNING")):
            matching = [e for e in events if e.level in levels]
            began = self.held(key, bool(matching), 0, now, matching[0].at if matching else None)
            if began:
                last = matching[-1]
                if any(e.level == "crit" for e in matching):
                    title = "API CRITICAL"
                count = f"{len(matching)}x: " if len(matching) > 1 else ""
                alert(key, severity, title, count + (last.detail or last.text), began)

    def backup_alerts(self, alert, now):
        """A failed nightly backup, or none for too long; returns when it last ran."""
        backup = self.fresh("backup", now) or {}
        exited = backup.get("ExecMainExitTimestamp")
        if exited and backup.get("Result") != "success":
            at = time.strftime("%H:%M", time.localtime(exited))
            alert("backup-failed", ERROR, "BACKUP FAILED",
                  f"exit {backup.get('ExecMainStatus')} at {at}", exited)
        timer = self.fresh("backup-timer", now) or {}
        # The service's own record is gone after a reboot; the timer's persists.
        last = exited if exited and backup.get("Result") == "success" else None
        last = last or timer.get("LastTriggerUSec")
        limit = self.config.backup_age * 3600
        if last and now - last > limit:
            alert("backup-old", WARNING, "BACKUP OLD", f"last one {fmt_age(now - last)} ago",
                  last + limit)
        return last

    def box_alerts(self, alert, box, now):
        c = self.config
        began = self.held("card-missing", box["card_free"] is None, 60.0, now)
        if began:
            alert("card-missing", WARNING, "NO BACKUP CARD", f"{c.backup_mount} not mounted",
                  began)
        for key, name, free, share in (("disk", "DISK", box["disk_free"], box["disk_share"]),
                                       ("card", "CARD", box["card_free"], box["card_share"])):
            if share is None:
                continue
            percent = 100 * share
            began = self.held(key, percent < c.free_warning, 0, now)
            if began:
                severity = ERROR if percent < c.free_error else WARNING
                title = f"{name} FULL" if severity == ERROR else f"{name} LOW"
                alert(key, severity, title, f"{free / GB:.1f} GB free ({percent:.0f} %)", began)

        # Without vcgencmd (the video group) under-voltage would go unseen.
        began = self.held("source-throttled", box["throttled"] is None, 180.0, now)
        if began:
            alert("source-throttled", WARNING, "SOURCE FAILING",
                  "vcgencmd get_throttled: no answer", began)
        bits = box["throttled"] or 0
        began = self.held("under-voltage", bool(bits & UNDER_VOLTAGE), 10.0, now)
        if began:
            alert("under-voltage", ERROR, "UNDER-VOLTAGE", "the power supply sags", began)
        slowed = [name for bit, name in ((CAPPED, "frequency capped"), (THROTTLED, "throttled"),
                                         (SOFT_LIMIT, "soft temperature limit")) if bits & bit]
        began = self.held("throttled", bool(slowed), 0, now)
        if began:
            alert("throttled", WARNING, "THROTTLED", ", ".join(slowed), began)
        seen = bool(bits & UNDER_VOLTAGE_SEEN) and not bits & UNDER_VOLTAGE
        began = self.held("under-voltage-seen", seen, 0, now)
        if began:
            alert("under-voltage-seen", WARNING, "UNDER-VOLTAGE", "seen since boot", began)

        temp = box["temp"]
        began = self.held("temp", temp is not None and temp > c.temp_warning, 60.0, now)
        if began:
            severity = ERROR if temp > c.temp_error else WARNING
            alert("temp", severity, "TOO HOT" if severity == ERROR else "HOT",
                  f"CPU {temp:.0f} °C", began)

    def source_alerts(self, alert, now, tunnel_down):
        """A source of the display that fails, or has gone quiet."""
        for name, every in EVERY.items():
            if name in ("health", "public") or (name == "ready" and tunnel_down):
                continue
            reading = self.store.get(name)
            if reading.fails >= 3:
                alert(f"source-{name}", WARNING, "SOURCE FAILING", f"{name}: {reading.error}",
                      reading.failing_since)
                continue
            last = reading.at or self.started
            silent = now - last > 3 * every + 10
            began = self.held(f"silent-{name}", silent, 0, now, last)
            if began:
                alert(f"source-{name}", WARNING, "SOURCE FAILING",
                      f"{name}: nothing for {fmt_age(now - last)}", began)
        journal = self.store.get("journal")
        if journal.fails >= 1 and journal.error:
            alert("source-journal", WARNING, "SOURCE FAILING", f"journal: {journal.error}",
                  journal.failing_since)


def alerts_with(alerts, keys):
    return [a for a in alerts if a.key in keys]
