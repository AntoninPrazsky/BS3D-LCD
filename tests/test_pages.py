"""The fonts draw every nickname, and every page fits the panel (#5)."""

import unicodedata
import unittest
from dataclasses import replace

from PIL import Image

from bs3d_lcd.font import Font, font_names
from bs3d_lcd.status import shots, strip
from bs3d_lcd.status.demo import ALERTS, DemoSource
from bs3d_lcd.status.pages import (HEIGHT, WIDTH, ActivityPage, AlertPage, BoxPage,
                                   RecoveredPage, ServerPage, TopPlayersPage, WarningsPage)
from bs3d_lcd.status.state import Alert, Play, Player, Server, State
from bs3d_lcd.status.ui import UI, fmt_age, fmt_int, fmt_span

UI_ = UI()


def nickname_letters():
    """The letters a BS3D nickname may hold: letters and digits up to U+017F, without
    U+0149 (the game's Game/Online/Nickname.cs), and space, _ and -."""
    return [chr(c) for c in range(0x20, 0x180)
            if (unicodedata.category(chr(c)) in ("Lu", "Ll", "Lt", "Lm", "Lo", "Nd")
                and c != 0x149) or chr(c) in " _-"]


class FontTest(unittest.TestCase):
    def test_every_font_draws_every_nickname_letter(self):
        for name in font_names():
            font = Font(name)
            with self.subTest(name):
                missing = [c for c in nickname_letters() if not font.has(c)]
                self.assertEqual(missing, [])

    def test_marks_stay_within_the_ascent(self):
        for name in font_names():
            font = Font(name)
            image = Image.new("L", (400, 40))
            font.draw(image, 0, 10 + font.ascent - font.cap, "ŘŠŽÁÉÍĚŮÝÔĽĹŐŰ")
            top = image.getbbox()[1]
            self.assertGreaterEqual(top, 10, name)

    def test_proportional_digits_keep_their_cells(self):
        font = Font("6x10")
        self.assertEqual(font.width("1111"), font.width("8888"))

    def test_bold_is_one_pixel_wider_per_letter(self):
        self.assertEqual(Font("6x10", bold=True, proportional=False).width("ABC"),
                         Font("6x10", proportional=False).width("ABC") + 3)


class FormatTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(fmt_int(1804320), "1 804 320")
        self.assertEqual(fmt_int(12), "12")

    def test_ages(self):
        self.assertEqual([fmt_age(s) for s in (5, 75, 7300, 200000)], ["5s", "1m", "2h", "2d"])
        self.assertEqual(fmt_age(-3), "0s")

    def test_spans(self):
        self.assertEqual(fmt_span(2 * 86400 + 4 * 3600 + 5), "2d 4h")
        self.assertEqual(fmt_span(3 * 3600 + 12 * 60), "3h 12m")
        self.assertEqual(fmt_span(42), "42s")


def states():
    """Made-up states: a busy day, an empty server, nothing read yet, old data,
    every alert at once, the longest nicknames."""
    busy = shots.demo_state()
    alerts = tuple(Alert(key, severity, title, detail, busy.now - 600)
                   for key, (severity, title, detail) in ALERTS.items())
    many = alerts + tuple(Alert(f"w{i}", "warning", f"WARNING NUMBER {i}", "", busy.now - 60 * i)
                          for i in range(6))
    longest = tuple(Player(i + 1, "ŘŽŠÁÉŮÝÍĚĎŤŇÓÚŮŘ"[:16], 9_999_999, 999, 2997)
                    for i in range(10))
    return {
        "busy": busy,
        "empty": State(now=busy.now, server=busy.server,
                       play=Play(at=busy.now, hours=(0,) * 24)),
        "unknown": State(now=busy.now),
        "offline": replace(busy, server=Server(at=busy.now, online=False)),
        "stale": replace(busy, play=replace(busy.play, at=busy.now - 3600)),
        "alerts": replace(busy, alerts=many),
        "longest": replace(busy, play=replace(busy.play, top_month=longest, top_all=longest)),
    }


class PagesTest(unittest.TestCase):
    PAGES = (ServerPage(UI_), ActivityPage(UI_), TopPlayersPage(UI_), WarningsPage(UI_),
             BoxPage(UI_),
             AlertPage(UI_), RecoveredPage(UI_, ("API DOWN", "TUNNEL DOWN"), 754))

    def test_every_page_renders_at_its_size(self):
        for name, state in states().items():
            for page in self.PAGES:
                if page.skip(state):
                    continue
                for t in (0.0, 5.0, 31.0):
                    with self.subTest(state=name, page=page.name, t=t):
                        image = page.render(state, t)
                        self.assertEqual(image.size, (WIDTH, HEIGHT))
                        self.assertEqual(image.mode, "L")

    def test_strip(self):
        for name, state in states().items():
            with self.subTest(name):
                image = strip.render(UI_, state, 1.0, 2, 4)
                self.assertEqual(image.size, (128, strip.HEIGHT))

    def test_pages_with_nothing_to_say_are_skipped(self):
        s = states()
        self.assertTrue(TopPlayersPage(UI_).skip(s["empty"]))
        self.assertTrue(WarningsPage(UI_).skip(s["busy"]))
        self.assertFalse(WarningsPage(UI_).skip(s["alerts"]))
        self.assertTrue(ActivityPage(UI_).skip(s["unknown"]))
        self.assertFalse(ServerPage(UI_).skip(s["unknown"]))

    def test_the_roll_leaves_as_it_came_in(self):
        page, state = TopPlayersPage(UI_, speed=12.0), states()["busy"]
        duration = page.duration(state, 8.0)
        self.assertGreater(duration, 20.0)
        self.assertEqual(page.render(state, 0.0).tobytes(),
                         page.render(state, duration).tobytes())
        self.assertNotEqual(page.render(state, 0.0).tobytes(),
                            page.render(state, duration / 2).tobytes())

    def test_the_roll_loops_without_a_jump(self):
        page, state = TopPlayersPage(UI_, speed=12.0, fade=False), states()["busy"]
        loop, lap = page._build(state)
        self.assertEqual(loop.crop((0, 0, WIDTH, HEIGHT)).tobytes(),
                         loop.crop((0, lap, WIDTH, lap + HEIGHT)).tobytes())

    def test_a_nickname_of_16_letters_with_marks_fits(self):
        page, state = TopPlayersPage(UI_, fade=False), states()["longest"]
        loop, _ = page._build(state)
        # Nothing touches the side edges.
        for x in (0, WIDTH - 1):
            column = loop.crop((x, 0, x + 1, loop.height))
            self.assertIsNone(column.getbbox())

    def test_stale_play_statistics_are_grey(self):
        s = states()
        fresh = ActivityPage(UI_).render(s["busy"], 1.0)
        stale = ActivityPage(UI_).render(s["stale"], 1.0)
        self.assertEqual(fresh.crop((0, 0, 60, 10)).getextrema()[1], 255)
        self.assertLess(stale.crop((0, 0, 60, 10)).getextrema()[1], 255)

    def test_demo_numbers_are_the_same_for_the_same_seed(self):
        a = DemoSource(start=0, wall=shots.WALL, script=False).state(5.0)
        b = DemoSource(start=0, wall=shots.WALL, script=False).state(5.0)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
