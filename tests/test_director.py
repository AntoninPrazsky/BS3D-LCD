"""The director's rotation, alarms, notes and button, on a made-up clock (#2, #3, #8)."""

import os
import shutil
import tempfile
import unittest
from dataclasses import replace

from bs3d_lcd.status.button import LONG, SHORT
from bs3d_lcd.status.director import Director
from bs3d_lcd.status.pages import AlertPage, NotePage, Page, RecoveredPage
from bs3d_lcd.status.seen import Seen, path_from_environment
from bs3d_lcd.status.state import ERROR, WARNING, Alert, Note, Play, Server, State
from bs3d_lcd.status.ui import UI, page

UI_ = UI()


class Blank(Page):
    def __init__(self, name, skip=False, duration=None):
        super().__init__(UI_)
        self.name, self._skip, self._duration = name, skip, duration

    def skip(self, state):
        return self._skip

    def duration(self, state, default):
        return self._duration or default

    def render(self, state, t):
        return page(128, 55)


class Source:
    """A state that the test changes as it goes."""

    def __init__(self):
        self.alerts = ()
        self.notes = None           # the snapshot's notes_recent; None: none written

    def __call__(self, now):
        # The play statistics as a snapshot gives them; notes_recent None as a service before BS3D-API#15
        play = Play(at=1_000_000 + now, notes_recent=self.notes)
        return State(now=1_000_000 + now, server=Server(at=1_000_000 + now, online=True),
                     play=play, alerts=self.alerts)


def error(key="api-down", since=1_000_000.0):
    return Alert(key, ERROR, key.upper(), "", since)


def note(at, kind="player", sender="Ann"):
    """A note that came ``at`` s into the test's clock."""
    return Note(1_000_000 + at, kind, sender)


class DirectorTest(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.pages = [Blank("a"), Blank("b"), Blank("c")]
        self.director = Director(UI_, self.source, self.pages, page_time=8.0, slide=1.0,
                                 state_every=0.0)
        self.t = 0.0

    def run_until(self, t, step=0.05):
        while self.t <= t + 1e-9:
            self.director.frame(self.t)
            self.t = round(self.t + step, 6)

    def shown(self):
        d = self.director
        return (d.slide.new if d.slide else d.screen).page

    def test_rotation_in_order_with_pushes(self):
        self.run_until(0.0)
        self.assertEqual(self.shown().name, "a")
        self.run_until(7.9)
        self.assertEqual(self.shown().name, "a")
        self.run_until(8.1)
        self.assertIsNotNone(self.director.slide)
        self.run_until(9.2)
        self.assertIsNone(self.director.slide)
        self.assertEqual(self.shown().name, "b")
        self.run_until(25.0)
        self.assertEqual(self.shown().name, "a")       # c, then round again

    def test_a_skipped_page_is_never_shown(self):
        self.pages[1]._skip = True
        seen = set()
        while self.t < 60:
            self.run_until(self.t)
            seen.add(self.shown().name)
        self.assertEqual(seen, {"a", "c"})

    def test_a_page_may_set_its_own_time(self):
        self.pages[0]._duration = 20.0
        self.run_until(19.0)
        self.assertEqual(self.shown().name, "a")
        self.run_until(21.0)
        self.assertEqual(self.shown().name, "b")

    def test_the_push_is_whole_pixels_and_eased(self):
        self.run_until(8.0)
        start = self.director.slide.start
        image, _ = self.director.frame(start + 0.35)
        self.assertEqual(image.size, (128, 64))

    def test_an_alarm_takes_over_at_once_and_sounds(self):
        self.run_until(3.0)
        self.source.alerts = (error(),)
        self.run_until(4.0)
        self.assertIsInstance(self.shown(), AlertPage)
        self.assertTrue(self.director.siren.on)
        self.run_until(30.0)
        self.assertIsInstance(self.shown(), AlertPage)  # it stays while the error stands

    def test_long_hold_acknowledges_and_the_rotation_goes_on(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.assertFalse(self.director.siren.on)
        self.assertNotIsInstance(self.shown(), AlertPage)
        self.run_until(40.0)
        self.assertFalse(self.director.siren.on)        # acknowledged: no siren again
        self.assertNotIsInstance(self.shown(), AlertPage)

    def test_a_new_error_sounds_again_after_an_acknowledgement(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.source.alerts = (error(), error("tunnel-down"))
        self.run_until(4.0)
        self.assertTrue(self.director.siren.on)
        self.assertIsInstance(self.shown(), AlertPage)

    def test_an_acknowledged_error_that_comes_back_sounds_again(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.source.alerts = ()
        self.run_until(4.0)
        self.source.alerts = (error(since=1_000_005.0),)
        self.run_until(6.0)
        self.assertTrue(self.director.siren.on)

    def test_long_hold_without_an_alarm_does_nothing(self):
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.assertEqual(self.shown().name, "a")
        self.assertIsNone(self.director.slide)

    def test_short_press_shows_the_next_page(self):
        self.run_until(2.0)
        self.director.press(SHORT)
        self.run_until(3.0)
        self.assertEqual(self.shown().name, "b")
        self.run_until(9.8)
        self.assertEqual(self.shown().name, "b")        # its full time from the push
        self.run_until(10.2)
        self.assertEqual(self.shown().name, "c")

    def test_short_press_during_an_alarm_browses_and_the_alert_comes_back(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.director.press(SHORT)
        self.run_until(3.0)
        self.assertNotIsInstance(self.shown(), AlertPage)
        self.assertTrue(self.director.siren.on)         # still sounding
        self.run_until(12.0)
        self.assertIsInstance(self.shown(), AlertPage)

    def test_button_edges_make_presses(self):
        self.run_until(2.0)
        self.director.edge("down", 2.0)
        self.director.edge("up", 2.2)
        self.run_until(3.0)
        self.assertEqual(self.shown().name, "b")

    def test_a_hold_fills_a_bar_only_while_the_siren_sounds(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.director.edge("down", 2.0)
        image, _ = self.director.frame(2.75)
        bar = [image.getpixel((x, 63)) for x in range(128)]
        self.assertEqual(bar[:60], [255] * 60)
        self.assertEqual(bar[70:], [0] * 58)
        self.run_until(3.6)
        self.assertFalse(self.director.siren.on)        # the hold reached 1.5 s

    def test_recovered_once_the_errors_clear(self):
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.source.alerts = ()
        self.run_until(3.0)
        self.assertIsInstance(self.shown(), RecoveredPage)
        self.assertFalse(self.director.siren.on)
        self.run_until(13.0)
        self.assertNotIsInstance(self.shown(), RecoveredPage)

    def test_a_warning_does_not_sound(self):
        self.source.alerts = (replace(error(), severity=WARNING),)
        self.run_until(5.0)
        self.assertFalse(self.director.siren.on)
        self.assertEqual(self.shown().name, "a")

    def levels(self, until, step=0.01):
        out = []
        while self.t < until:
            out.append(self.director.frame(self.t)[1])
            self.t = round(self.t + step, 6)
        return out

    def test_the_notes_there_at_the_first_start_count_as_seen(self):
        self.source.notes = (note(-60), note(-600))
        self.run_until(3.0)
        self.assertEqual(self.director.seen.at, note(-60).at)
        self.assertFalse(self.director.knock.on)
        self.assertEqual(self.shown().name, "a")
        self.assertEqual(set(self.levels(8.0)), {1.0})

    def test_a_new_note_takes_over_and_knocks_until_held(self):
        self.source.notes = (note(-60),)
        self.run_until(2.0)
        self.source.notes = (note(2.5), note(-60))
        self.run_until(3.0)
        self.assertIsInstance(self.shown(), NotePage)
        self.assertTrue(self.director.knock.on)
        self.assertEqual(self.director.frame(self.t)[0].getpixel((0, 10)), 255)     # its header, inverted
        levels = self.levels(11.0)
        self.assertAlmostEqual(min(levels), 0.9, places=2)
        self.assertEqual(max(levels), 1.0)
        self.assertIsInstance(self.shown(), NotePage)   # it stays until acknowledged

    def test_long_hold_acknowledges_every_note_and_a_later_one_knocks_again(self):
        self.source.notes = ()
        self.run_until(1.0)
        self.source.notes = (note(1.5), note(1.2))
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.assertEqual(self.director.seen.at, note(1.5).at)
        self.assertNotIsInstance(self.shown(), NotePage)
        self.run_until(30.0)
        self.assertFalse(self.director.knock.on)
        self.assertNotIsInstance(self.shown(), NotePage)
        self.source.notes = (note(30.5), note(1.5), note(1.2))
        self.run_until(31.0)
        self.assertTrue(self.director.knock.on)
        self.assertIsInstance(self.shown(), NotePage)

    def test_a_note_that_takes_a_deleted_note_s_id_still_knocks(self):
        # The panel knows notes by when they came: a deleted note's id coming again changes nothing
        self.source.notes = (note(-60),)
        self.run_until(2.0)
        self.source.notes = (note(2.5, sender="Bob"),)  # the note of -60 deleted, a new one in
        self.run_until(3.0)
        self.assertTrue(self.director.knock.on)

    def test_an_error_comes_first_and_one_hold_acknowledges_both(self):
        self.source.notes = ()
        self.run_until(1.0)
        self.source.notes = (note(1.5),)
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.assertIsInstance(self.shown(), AlertPage)
        self.assertTrue(self.director.siren.on)
        self.assertFalse(self.director.knock.on)
        self.assertGreater(max(self.levels(4.0)), 1.1)  # the siren's swing, not the knock
        self.director.press(LONG)
        self.run_until(5.0)
        self.assertFalse(self.director.siren.on)
        self.assertFalse(self.director.knock.on)
        self.assertEqual(self.director.seen.at, note(1.5).at)
        self.assertNotIsInstance(self.shown(), (AlertPage, NotePage))

    def test_once_the_error_clears_the_note_takes_its_place(self):
        self.source.notes = ()
        self.run_until(1.0)
        self.source.notes = (note(1.5),)
        self.source.alerts = (error(),)
        self.run_until(2.0)
        self.source.alerts = ()
        self.run_until(3.5)
        self.run_until(14.0)
        self.assertIsInstance(self.shown(), NotePage)
        self.assertTrue(self.director.knock.on)

    def test_short_press_during_a_note_browses_and_the_note_comes_back(self):
        self.source.notes = ()
        self.run_until(1.0)
        self.source.notes = (note(1.5),)
        self.run_until(3.0)
        self.director.press(SHORT)
        self.run_until(4.5)
        self.assertNotIsInstance(self.shown(), NotePage)
        self.assertTrue(self.director.knock.on)
        self.run_until(14.0)
        self.assertIsInstance(self.shown(), NotePage)

    def test_a_snapshot_without_notes_watches_nothing(self):
        self.source.notes = None
        self.run_until(5.0)
        self.assertIsNone(self.director.seen.at)
        self.assertFalse(self.director.knock.on)
        self.director.press(LONG)
        self.run_until(6.0)
        self.assertEqual(self.shown().name, "a")

    def test_a_hold_fills_the_bar_while_a_note_knocks(self):
        self.source.notes = ()
        self.run_until(1.0)
        self.source.notes = (note(1.5),)
        self.run_until(3.0)
        self.director.edge("down", 3.0)
        image, _ = self.director.frame(3.75)
        self.assertEqual([image.getpixel((x, 63)) for x in range(60)], [255] * 60)

    def test_the_acknowledgement_outlives_a_restart(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "notes-seen")
        self.source.notes = ()
        self.director = Director(UI_, self.source, self.pages, state_every=0.0, seen=Seen(path))
        self.run_until(1.0)
        self.source.notes = (note(1.5),)
        self.run_until(2.0)
        self.director.press(LONG)
        self.run_until(3.0)
        self.assertEqual(Seen(path).at, note(1.5).at)

        # The service restarts: the same notes, nothing to knock for
        self.director, self.t = Director(UI_, self.source, self.pages, state_every=0.0, seen=Seen(path)), 0.0
        self.run_until(3.0)
        self.assertFalse(self.director.knock.on)
        # A note sent while it was down still knocks
        self.source.notes = (note(2.5), note(1.5))
        self.director, self.t = Director(UI_, self.source, self.pages, state_every=0.0, seen=Seen(path)), 0.0
        self.run_until(3.0)
        self.assertTrue(self.director.knock.on)

    def test_the_level_follows_the_siren(self):
        self.run_until(1.0)
        _, level = self.director.frame(1.0)
        self.assertEqual(level, 1.0)
        self.source.alerts = (error(),)
        levels = []
        while self.t < 4.0:
            levels.append(self.director.frame(self.t)[1])
            self.t += 0.01
        self.assertLess(min(levels), 0.9)
        self.assertGreater(max(levels), 1.1)


class SeenTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = os.path.join(self.folder, "notes-seen")
        self.lines = []

    def test_none_until_set_then_kept_in_the_file(self):
        seen = Seen(self.path)
        self.assertIsNone(seen.at)
        seen.set(1_761_510_000.123456)
        self.assertEqual(Seen(self.path).at, 1_761_510_000.123456)
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_a_file_that_does_not_read_counts_as_none_and_says_so(self):
        with open(self.path, "w") as f:
            f.write("garbage")
        self.assertIsNone(Seen(self.path, log=self.lines.append).at)
        self.assertEqual(len(self.lines), 1)

    def test_one_that_cannot_be_written_is_kept_in_memory(self):
        seen = Seen(os.path.join(self.folder, "missing", "notes-seen"), log=self.lines.append)
        seen.set(5.0)
        self.assertEqual(seen.at, 5.0)
        self.assertEqual(len(self.lines), 1)

    def test_the_path_is_the_state_directory_s(self):
        self.assertEqual(path_from_environment({"STATE_DIRECTORY": "/var/lib/bs3d-lcd"}),
                         "/var/lib/bs3d-lcd/notes-seen")
        self.assertEqual(path_from_environment({"STATE_DIRECTORY": "/a:/b"}), "/a/notes-seen")
        self.assertIsNone(path_from_environment({}))


if __name__ == "__main__":
    unittest.main()
