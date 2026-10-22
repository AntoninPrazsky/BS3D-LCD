"""The conditions of #4: each alerts after its hold and not before, and clears again."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from bs3d_lcd.status import snapshot
from bs3d_lcd.status.config import Config, load
from bs3d_lcd.status.monitor import Monitor
from bs3d_lcd.status.sources import LogEvent, Reading, Store, describe, parse_journal
from bs3d_lcd.status.state import ERROR, WARNING

T0 = 1_800_000_000.0
GB = 10 ** 9


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def healthy_box(**changes):
    box = {"host": "pi", "uptime": 1000.0, "temp": 50.0, "throttled": 0, "fan": 2000,
           "load": 0.5, "memory": 0.3, "disk_free": 400 * GB, "disk_share": 0.88,
           "card_free": 120 * GB, "card_share": 0.99}
    box.update(changes)
    return box


class MonitorCase(unittest.TestCase):
    """A monitor over a store the test fills, on a clock the test moves."""

    def setUp(self):
        self.clock = Clock()
        self.store = Store(clock=self.clock)
        self.config = Config(public_health="https://example.invalid/v1/health")
        self.monitor = Monitor(self.config, self.store, clock=self.clock)
        self.service = {"ActiveState": "active", "SubState": "running", "NRestarts": "0",
                        "ActiveEnterTimestamp": T0 - 3600}
        self.box = healthy_box()
        self.health_ok = True
        self.health_answer = {"status": "ok", "boards": 176}
        self.tunnel = {"ActiveState": "active", "SubState": "running"}
        self.connections = 4
        self.public_ok = True
        self.backup = {"Result": "success", "ExecMainStatus": "0",
                       "ExecMainExitTimestamp": T0 - 3600}

    def tick(self, seconds=0.0):
        """Every source reads once, then time moves on."""
        s = self.store
        s.ok("service", dict(self.service))
        if self.health_ok:
            s.ok("health", self.health_answer)
        else:
            s.fail("health", "refused")
        s.ok("tunnel", self.tunnel)
        s.ok("ready", self.connections)
        s.ok("release", "v0.1.26")
        s.ok("backup", self.backup)
        s.ok("backup-timer", {"LastTriggerUSec": self.backup["ExecMainExitTimestamp"]})
        s.ok("box", self.box)
        if self.public_ok:
            s.ok("public", {"status": "ok"})
        else:
            s.fail("public", "HTTP 530")
        state = self.monitor.state()
        self.clock.t += seconds
        return state

    def run_for(self, seconds, step=5.0):
        state = None
        end = self.clock.t + seconds
        while self.clock.t <= end:
            state = self.tick(step)
        return state

    def keys(self, state):
        return {a.key: a.severity for a in state.alerts}

class MonitorTest(MonitorCase):
    def test_all_well(self):
        state = self.run_for(30)
        self.assertEqual(state.alerts, ())
        self.assertTrue(state.server.online)
        self.assertEqual(state.server.version, "v0.1.26")
        self.assertEqual(state.server.tunnel, 4)
        self.assertEqual(state.server.since, T0 - 3600)
        self.assertEqual(state.box.host, "pi")

    def test_nothing_read_yet_is_starting(self):
        self.assertIsNone(self.monitor.state().server)

    def test_service_down_after_its_hold(self):
        self.run_for(10)
        self.service["ActiveState"], self.service["SubState"] = "inactive", "dead"
        state = self.run_for(15)
        self.assertNotIn("service-down", self.keys(state))
        self.assertTrue(state.server.online)
        state = self.run_for(10)
        self.assertEqual(self.keys(state).get("service-down"), ERROR)
        self.assertFalse(state.server.online)
        self.service["ActiveState"] = "active"
        state = self.tick()
        self.assertNotIn("service-down", self.keys(state))
        self.assertTrue(state.server.online)

    def test_a_deploy_restart_does_not_alert(self):
        self.run_for(10)
        self.service["ActiveState"] = "deactivating"
        self.run_for(10)
        self.service["ActiveState"] = "active"
        state = self.run_for(30)
        self.assertEqual(state.alerts, ())

    def test_health_after_three_failed_checks(self):
        self.run_for(10)
        self.health_ok = False
        self.tick(10)
        state = self.tick(10)
        self.assertNotIn("health", self.keys(state))
        state = self.tick(10)
        alert = next(a for a in state.alerts if a.key == "health")
        self.assertEqual(alert.severity, ERROR)
        self.assertEqual(alert.detail, "health: refused")
        self.assertEqual(alert.since, T0 + 15)        # the first failed check
        self.assertFalse(state.server.online)
        self.health_ok = True
        self.assertEqual(self.tick().alerts, ())

    def test_a_stopped_service_is_api_down_not_no_answer(self):
        self.run_for(5)
        self.service["ActiveState"] = "inactive"
        self.health_ok = False
        state = self.run_for(40)
        self.assertEqual(list(self.keys(state)), ["service-down"])

    def test_no_boards(self):
        self.health_answer = {"status": "ok", "boards": 0}
        self.assertNotIn("no-boards", self.keys(self.run_for(10)))
        self.assertEqual(self.keys(self.run_for(10)).get("no-boards"), ERROR)

    def test_tunnel_after_a_minute(self):
        self.run_for(5)
        self.connections = 0
        self.assertNotIn("tunnel", self.keys(self.run_for(50)))
        state = self.run_for(15)
        self.assertEqual(self.keys(state).get("tunnel"), ERROR)
        self.assertFalse(state.server.online)

    def test_tunnel_unit_down(self):
        self.tunnel = {"ActiveState": "failed", "SubState": "failed"}
        state = self.run_for(70)
        alert = next(a for a in state.alerts if a.key == "tunnel")
        self.assertEqual(alert.detail, "cloudflared: failed")

    def test_unreachable_from_outside(self):
        self.public_ok = False
        self.tick(60)
        state = self.tick(60)
        self.assertNotIn("public", self.keys(state))
        state = self.tick(60)
        self.assertEqual(self.keys(state).get("public"), ERROR)
        self.assertFalse(state.server.online)

    def test_unreachable_is_not_said_when_the_service_is_down(self):
        self.public_ok = False
        self.service["ActiveState"] = "failed"
        state = self.run_for(200, step=60)
        self.assertIn("service-down", self.keys(state))
        self.assertNotIn("public", self.keys(state))

    def test_restarts(self):
        self.run_for(10)
        self.service["NRestarts"] = "1"
        state = self.tick(60)
        self.assertEqual(self.keys(state).get("restarts"), WARNING)
        self.service["NRestarts"] = "3"
        state = self.tick(60)
        self.assertEqual(self.keys(state).get("restarts"), ERROR)
        self.clock.t += 2 * 3600
        self.assertEqual(self.keys(self.tick()).get("restarts"), WARNING)
        self.clock.t += 86400
        self.assertNotIn("restarts", self.keys(self.tick()))

    def test_logged_errors_stand_for_the_window(self):
        self.run_for(10)
        self.store.event(LogEvent(self.clock.t, "fail", "BS3D.Api.Endpoints[0]", "boom"))
        state = self.tick(60)
        alert = next(a for a in state.alerts if a.key == "log-error")
        self.assertEqual((alert.severity, alert.title, alert.detail), (ERROR, "API ERROR", "boom"))
        first = alert.since
        self.store.event(LogEvent(self.clock.t, "fail", "BS3D.Api.Endpoints[0]", "again"))
        self.clock.t += 14 * 60
        alert = next(a for a in self.tick().alerts if a.key == "log-error")
        self.assertEqual(alert.since, first)            # the same occurrence
        self.assertEqual(alert.detail, "2x: again")
        self.clock.t += 2 * 60
        self.assertNotIn("log-error", self.keys(self.tick()))

    def test_logged_warning_and_critical(self):
        self.store.event(LogEvent(self.clock.t, "warn", "X[0]", "slow"))
        self.store.event(LogEvent(self.clock.t, "crit", "X[0]", "dead"))
        state = self.tick()
        self.assertEqual(self.keys(state).get("log-warning"), WARNING)
        alert = next(a for a in state.alerts if a.key == "log-error")
        self.assertEqual(alert.title, "API CRITICAL")

    def test_backup_failed_and_old(self):
        self.backup = {"Result": "exit-code", "ExecMainStatus": "2",
                       "ExecMainExitTimestamp": T0 - 600}
        state = self.tick()
        alert = next(a for a in state.alerts if a.key == "backup-failed")
        self.assertEqual((alert.severity, alert.since), (ERROR, T0 - 600))
        self.backup = {"Result": "success", "ExecMainStatus": "0",
                       "ExecMainExitTimestamp": T0 - 27 * 3600}
        state = self.tick()
        self.assertNotIn("backup-failed", self.keys(state))
        self.assertEqual(self.keys(state).get("backup-old"), WARNING)
        self.assertEqual(state.box.backup_at, T0 - 27 * 3600)

    def test_card_missing_and_space(self):
        self.box = healthy_box(card_free=None, card_share=None)
        self.assertNotIn("card-missing", self.keys(self.run_for(50)))
        self.assertEqual(self.keys(self.run_for(20)).get("card-missing"), WARNING)
        self.box = healthy_box(disk_free=30 * GB, disk_share=0.07)
        self.assertEqual(self.keys(self.tick()).get("disk"), WARNING)
        self.box = healthy_box(disk_free=10 * GB, disk_share=0.02)
        alert = next(a for a in self.tick().alerts if a.key == "disk")
        self.assertEqual((alert.severity, alert.title), (ERROR, "DISK FULL"))

    def test_power_and_heat(self):
        self.box = healthy_box(throttled=0x1)
        self.assertNotIn("under-voltage", self.keys(self.tick(5)))
        self.assertEqual(self.keys(self.run_for(10)).get("under-voltage"), ERROR)
        self.box = healthy_box(throttled=0x50000 | 0x4)
        state = self.tick()
        self.assertEqual(self.keys(state).get("throttled"), WARNING)
        self.assertEqual(self.keys(state).get("under-voltage-seen"), WARNING)
        self.box = healthy_box(temp=82.0)
        self.assertNotIn("temp", self.keys(self.run_for(50)))
        self.assertEqual(self.keys(self.run_for(15)).get("temp"), WARNING)
        self.box = healthy_box(temp=87.0)
        alert = next(a for a in self.tick().alerts if a.key == "temp")
        self.assertEqual((alert.severity, alert.title), (ERROR, "TOO HOT"))

    def test_no_throttling_reading_is_a_warning(self):
        self.box = healthy_box(throttled=None)
        self.assertNotIn("source-throttled", self.keys(self.run_for(170)))
        self.assertEqual(self.keys(self.run_for(20)).get("source-throttled"), WARNING)

    def test_a_source_that_fails_or_goes_quiet(self):
        self.run_for(10)
        for _ in range(3):
            self.store.fail("box", "vcgencmd: timeout")
        state = self.monitor.state()
        self.assertEqual(self.keys(state).get("source-box"), WARNING)
        # The release is read once a minute; quiet for over 3 minutes is a failure.
        self.clock.t += 200
        self.store.ok("service", self.service)
        state = self.monitor.state()
        self.assertIn("source-release", self.keys(state))

    def test_old_readings_are_not_used(self):
        self.tick()
        self.clock.t += 600
        state = self.monitor.state()
        self.assertIsNone(state.box)
        self.assertIsNone(state.server.tunnel)

    def test_errors_come_first(self):
        self.box = healthy_box(throttled=0x4)
        self.service["ActiveState"] = "failed"
        state = self.run_for(30)
        self.assertEqual(state.alerts[0].severity, ERROR)


def iso(t):
    """A moment as BS3D-API writes it: ISO 8601 with seven decimals."""
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f0+00:00")


def status(at, refusals=None, offbox=None, offsite=None):
    """A status snapshot as BS3D-API's admin status-feed writes it (its #13)."""
    return {
        "format": 1, "written_at": iso(at),
        "service": {"version": "0.1.27+abc", "schema": 4, "expected_schema": 4, "db_bytes": 184320},
        "totals": {"players": 4, "clears": 102, "attempts": 23, "boards": 176, "boards_with_clear": 61,
                   "notes": 3},
        "today": {"day": "2026-10-22", "zone": "Europe/Prague", "clears": 5, "attempts": 2,
                  "new_players": 1, "active_players": 3, "seconds_played": 912.5,
                  "refusals": {"rate-limited": 1}},
        "refusals_last_hour": refusals or {},
        "hours": [0] * 23 + [4],
        "last_submission_at": iso(at - 60),
        "latest": [{"level": "Pagoda", "player": "Ann", "stars": 3, "score": 39707, "at": iso(at - 60)}],
        "top": {"rules": 1, "month": "2026-10",
                "this_month": [{"rank": 1, "name": "Ann", "levels": 2, "stars": 7, "score": 350}],
                "all_time": [{"rank": 1, "name": "Ann", "levels": 3, "stars": 9, "score": 500},
                             {"rank": 2, "name": "Bob", "levels": 1, "stars": 3, "score": 300}]},
        "backups": {"offbox": offbox, "offsite": offsite},
        "play": {"starts": 10, "clears": 4, "seconds": 600.0},
    }


class SnapshotTest(MonitorCase):
    """BS3D-API's status snapshot (its #13): the play pages' data, and what it warns about."""

    def setUp(self):
        super().setUp()
        self.snapshot = status(T0)

    def tick(self, seconds=0.0):
        if self.snapshot is not None:
            self.store.ok("snapshot", self.snapshot)
        else:
            self.store.fail("snapshot", "no such file or directory")
        return super().tick(seconds)

    def test_the_play_comes_from_the_snapshot(self):
        play = self.tick().play
        self.assertEqual((play.clears_today, play.attempts_today, play.players_today,
                          play.new_players_today, play.seconds_today), (5, 2, 3, 1, 912.5))
        self.assertEqual((play.players, play.clears, play.boards, play.boards_cleared, play.notes),
                         (4, 102, 176, 61, 3))
        self.assertEqual(play.hours[-1], 4)
        self.assertAlmostEqual(play.at, T0, places=3)
        self.assertAlmostEqual(play.last_score_at, T0 - 60, places=3)
        self.assertEqual([(p.rank, p.name, p.score) for p in play.top_all], [(1, "Ann", 500), (2, "Bob", 300)])
        self.assertEqual((play.latest[0].level, play.latest[0].player, play.latest[0].stars),
                         ("Pagoda", "Ann", 3))

    def test_old_statistics_are_a_warning_while_the_service_runs(self):
        self.assertNotIn("stats", self.keys(self.run_for(110)))
        state = self.run_for(20)
        alert = next(a for a in state.alerts if a.key == "stats")
        self.assertEqual((alert.severity, alert.title), (WARNING, "STATS OLD"))
        self.service["ActiveState"] = "failed"
        self.assertNotIn("stats", self.keys(self.tick()))     # API DOWN says it

    def test_no_snapshot_is_a_warning_after_two_minutes(self):
        self.snapshot = None
        state = self.run_for(110)
        self.assertNotIn("stats", self.keys(state))
        self.assertIsNone(state.play)
        alert = next(a for a in self.run_for(20).alerts if a.key == "stats")
        self.assertEqual((alert.title, alert.detail), ("NO STATS", "snapshot: no such file or directory"))
        self.assertNotIn("source-snapshot", self.keys(self.tick()))

    def test_refusals(self):
        for refusals, expected in (({"rate-limited": 5}, False), ({"bad-version": 1}, True),
                                   ({"unknown-board": 2, "rate-limited": 1}, True),
                                   ({"over-ceiling": 2}, False), ({"over-ceiling": 2, "wrong-token": 1}, True),
                                   ({"rate-limited": 31}, True)):
            with self.subTest(refusals):
                self.snapshot = status(self.clock.t, refusals)
                self.assertEqual("refusals" in self.keys(self.tick()), expected)
        alert = next(a for a in self.tick().alerts if a.key == "refusals")
        self.assertEqual(alert.detail, "31 rate-limited in 1 h")

    def test_a_failed_copy_is_an_error_and_an_old_one_a_warning(self):
        failed = {"result": "failed", "attempt": iso(T0 - 600), "ok": iso(T0 - 86000), "every": 1}
        self.snapshot = status(T0, offbox=failed)
        alert = next(a for a in self.tick().alerts if a.key == "copy-offbox")
        self.assertEqual((alert.severity, alert.title, alert.detail[:12]), (ERROR, "COPY FAILED", "off the box,"))
        # Off the site every two days: 49 h is on time, 51 h is late
        on_time = {"result": "ok", "attempt": iso(T0 - 49 * 3600), "ok": iso(T0 - 49 * 3600), "every": 2}
        self.snapshot = status(T0, offsite=on_time)
        self.assertNotIn("copy-offsite-old", self.keys(self.tick()))
        late = dict(on_time, ok=iso(T0 - 51 * 3600))
        self.snapshot = status(T0, offsite=late)
        self.assertEqual(self.keys(self.tick()).get("copy-offsite-old"), WARNING)
        self.assertEqual(self.keys(self.tick()).get("copy-offsite-old"), WARNING)

    def test_the_box_shows_the_copy_off_the_box(self):
        good = {"result": "ok", "attempt": iso(T0 - 3600), "ok": iso(T0 - 3600), "every": 1}
        self.snapshot = status(T0, offbox=good)
        self.assertAlmostEqual(self.tick().box.backup_at, T0 - 3600, places=3)

    def test_a_copy_not_set_up_says_nothing(self):
        self.snapshot = status(T0, offsite={"result": "none", "attempt": None, "ok": None, "every": 2})
        keys = self.keys(self.tick())
        self.assertFalse(any(k.startswith("copy-") for k in keys))

    def test_the_file_is_read_and_its_format_checked(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(status(T0), f)
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(snapshot.read(f.name)["format"], 1)
        with open(f.name, "w") as g:
            json.dump(dict(status(T0), format=2), g)
        with self.assertRaises(ValueError):
            snapshot.read(f.name)


class JournalTest(unittest.TestCase):
    def entry(self, message, priority=6):
        return json.dumps({"MESSAGE": message, "PRIORITY": str(priority),
                           "__REALTIME_TIMESTAMP": "1792232730658172"})

    def test_console_logger_prefixes(self):
        self.assertEqual(parse_journal(self.entry("fail: BS3D.Api.Endpoints[0]"))[:2],
                         ("fail", "BS3D.Api.Endpoints[0]"))
        self.assertEqual(parse_journal(self.entry("warn: X[3]"))[0], "warn")
        self.assertIsNone(parse_journal(self.entry("info: Microsoft.Hosting.Lifetime[0]"))[0])
        level, text, at = parse_journal(self.entry("      Now listening on: http://..."))
        self.assertIsNone(level)
        self.assertAlmostEqual(at, 1792232730.658172)

    def test_priorities_once_the_service_sets_them(self):
        self.assertEqual(parse_journal(self.entry("Something broke", 3))[0], "fail")
        self.assertEqual(parse_journal(self.entry("Careful", 4))[0], "warn")

    def test_binary_message(self):
        level, text, _ = parse_journal(json.dumps({"MESSAGE": list(b"fail: X[0]"),
                                                   "PRIORITY": "6"}))
        self.assertEqual((level, text), ("fail", "X[0]"))


class SourcesTest(unittest.TestCase):
    def test_store_counts_failures_in_a_row(self):
        clock = Clock()
        store = Store(clock=clock)
        store.ok("a", 1)
        store.fail("a", "x")
        clock.t += 10
        store.fail("a", "y")
        reading = store.get("a")
        self.assertEqual((reading.value, reading.fails, reading.error), (1, 2, "y"))
        self.assertEqual(reading.failing_since, T0)
        store.ok("a", 2)
        self.assertEqual(store.get("a"), Reading(2, clock.t))

    def test_describe(self):
        self.assertEqual(describe(TimeoutError()), "timeout")
        self.assertEqual(describe(ConnectionRefusedError(111, "Connection refused")), "refused")


class ConfigTest(unittest.TestCase):
    def write(self, text):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(lambda: __import__("os").unlink(f.name))
        return f.name

    def test_defaults_and_overrides(self):
        config = load(self.write('[sources]\npublic_health = "https://x/v1/health"\n'
                                 '[thresholds]\ntemp_warning = 75\n'))
        self.assertEqual(config.public_health, "https://x/v1/health")
        self.assertEqual(config.temp_warning, 75)
        self.assertEqual(config.service, "bs3d-api")

    def test_unknown_settings_are_refused(self):
        with self.assertRaises(ValueError):
            load(self.write("[sources]\ntemp_warning = 1\n"))
        with self.assertRaises(ValueError):
            load(self.write("[other]\nx = 1\n"))


if __name__ == "__main__":
    unittest.main()
