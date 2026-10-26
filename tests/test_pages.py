"""The fonts draw every nickname, and every page fits the panel (#5)."""

import unicodedata
import unittest
from dataclasses import replace

from PIL import Image

from bs3d_lcd.font import Font, font_names
from bs3d_lcd.status import shots, strip
from bs3d_lcd.status.demo import ALERTS, DemoSource
from bs3d_lcd.status.pages import (HEIGHT, WIDTH, ActivityPage, AlertPage, AllTimePage, BoxPage,
                                   LatestPlayersPage, LatestScoresPage, RecoveredPage, ServerPage,
                                   TodayPage, TopPlayersPage, WarningsPage)
from bs3d_lcd.status.state import Alert, Clear, Play, Player, RecentPlayer, Server, State
from bs3d_lcd.status.ui import GREY, UI, fmt_age, fmt_int, fmt_span, page

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


def page_with(draw):
    image = page(WIDTH, HEIGHT)
    draw(image)
    return image


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
    long_clears = tuple(Clear("Pagoda", "ŘŽŠÁÉŮÝÍĚĎŤŇÓÚŮŘ", 4, 9_999_999, busy.now - 23 * 3600) for _ in range(9))
    long_players = tuple(RecentPlayer("ŘŽŠÁÉŮÝÍĚĎŤŇÓÚŮŘ", busy.now - 59 * 60, 99, 99, True) for _ in range(9))
    return {
        "busy": busy,
        "empty": State(now=busy.now, server=busy.server,
                       play=Play(at=busy.now, hours=(0,) * 24)),
        "unknown": State(now=busy.now),
        "offline": replace(busy, server=Server(at=busy.now, online=False)),
        "stale": replace(busy, play=replace(busy.play, at=busy.now - 3600)),
        "alerts": replace(busy, alerts=many),
        "longest": replace(busy, play=replace(busy.play, top_month=longest, top_all=longest,
                                              recent=long_clears, recent_players=long_players)),
    }


class PagesTest(unittest.TestCase):
    PAGES = (ServerPage(UI_), TodayPage(UI_), LatestScoresPage(UI_), LatestPlayersPage(UI_),
             ActivityPage(UI_), TopPlayersPage(UI_), AllTimePage(UI_), WarningsPage(UI_), BoxPage(UI_),
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

    def test_the_page_dots_never_reach_the_clock(self):
        state = states()["busy"]
        edge = strip.clock(UI_, page(WIDTH, strip.HEIGHT), state.now, WIDTH // 2 + 6)
        from bs3d_lcd.status.pages import rotation
        for count in range(2, len(rotation(UI_)) + 2):
            with self.subTest(count=count):
                image = strip.render(UI_, state, 1.0, 0, count)
                self.assertIsNone(image.crop((edge, 2, edge + 2, 5)).getbbox())
                row = [image.getpixel((x, 3)) > 0 for x in range(edge + 2, WIDTH)]
                runs = sum(1 for i, on in enumerate(row) if on and (i == 0 or not row[i - 1]))
                self.assertEqual(runs, count)

    def test_pages_with_nothing_to_say_are_skipped(self):
        s = states()
        self.assertTrue(TopPlayersPage(UI_).skip(s["empty"]))
        self.assertTrue(WarningsPage(UI_).skip(s["busy"]))
        self.assertFalse(WarningsPage(UI_).skip(s["alerts"]))
        self.assertTrue(ActivityPage(UI_).skip(s["unknown"]))
        self.assertTrue(LatestScoresPage(UI_).skip(s["empty"]))
        self.assertTrue(LatestPlayersPage(UI_).skip(s["empty"]))
        self.assertFalse(LatestScoresPage(UI_).skip(s["busy"]))
        self.assertFalse(LatestPlayersPage(UI_).skip(s["busy"]))
        self.assertFalse(TodayPage(UI_).skip(s["empty"]))
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

    def test_the_latest_scores_and_players_fit_with_the_longest_nicknames(self):
        state = states()["longest"]
        for page in (LatestScoresPage(UI_), LatestPlayersPage(UI_)):
            for t in (0.0, 2 * page.turn + 1.0):
                with self.subTest(page=page.name, t=t):
                    image = page.render(state, t)
                    self.assertEqual(image.size, (WIDTH, HEIGHT))
                    # The third row's second line, descenders included, ends on the page's last row at most
                    last = page.TOP + (page.ROWS - 1) * page.PITCH + 10
                    self.assertLessEqual(last + UI_.tiny.cap + UI_.tiny.descent, HEIGHT)
                    # A long nickname takes a narrower font rather than running into the stars or NEW
                    self.assertIsNone(image.crop((WIDTH - 27, 2, WIDTH - 26, 9)).getbbox())
                    # Nothing runs into the column of the sets
                    self.assertIsNone(image.crop((WIDTH - page.BAR - 2, 0, WIDTH - page.BAR, HEIGHT)).getbbox())

    def test_nine_scores_take_three_sets_of_three_pushed_up_in_turn(self):
        page, state = LatestScoresPage(UI_), states()["busy"]
        self.assertEqual(len(state.play.recent), 9)
        self.assertEqual(page.duration(state, 8.0), 3 * page.turn)
        self.assertEqual(page.position(3, 0.0), (0, 0))
        self.assertEqual(page.position(3, page.turn - 0.01), (0, 0))
        index, offset = page.position(3, page.turn + page.slide / 2)
        self.assertEqual(index, 1)
        self.assertTrue(0 < offset < HEIGHT)
        self.assertEqual(page.position(3, page.turn + page.slide), (1, HEIGHT))
        self.assertEqual(page.position(3, 99.0), (2, 2 * HEIGHT))
        # The column: the current set dark, the others grey
        for t, on in ((0.0, 0), (page.turn + page.slide, 1), (2 * page.turn + page.slide, 2)):
            image = page.render(state, t)
            shades = [image.getpixel((WIDTH - 1, i * HEIGHT // 3 + 8)) for i in range(3)]
            self.assertEqual(shades, [255 if i == on else GREY for i in range(3)])
        self.assertNotEqual(page.render(state, 0.0).tobytes(),
                            page.render(state, page.turn + page.slide).tobytes())

    def test_one_set_stays_its_time_with_no_column(self):
        page, state = LatestScoresPage(UI_), states()["busy"]
        state = replace(state, play=replace(state.play, recent=state.play.recent[:3]))
        self.assertEqual(page.duration(state, 8.0), 8.0)
        # Between the first row and the second the column would be the only thing drawn
        self.assertEqual(page.render(state, 1.0).getpixel((WIDTH - 1, page.TOP + page.PITCH - 1)), 0)
        three = replace(state, play=replace(state.play, recent=state.play.recent * 2))
        self.assertEqual(page.render(three, 1.0).getpixel((WIDTH - 1, page.TOP + page.PITCH - 1)), 255)
        state = replace(state, play=replace(state.play, recent=state.play.recent[:2] * 2))
        self.assertEqual(page.duration(state, 8.0), 2 * page.turn)

    def test_an_unfinished_attempt_has_a_grey_zero_and_star(self):
        page, state = LatestScoresPage(UI_), states()["busy"]
        for stars, dark in ((0, GREY), (3, 255)):
            row = Clear("Pagoda", "Ann", stars, 21_380, state.now - 60)
            image = page.render(replace(state, play=replace(state.play, recent=(row,))), 1.0)
            self.assertEqual(image.crop((WIDTH - 16, 2, WIDTH, 9)).getextrema()[1], dark, stars)

    def test_without_the_newest_submissions_the_clears_are_shown(self):
        page, state = LatestScoresPage(UI_), states()["busy"]
        older = replace(state, play=replace(state.play, recent=()))
        self.assertEqual(page.rows(older), state.play.latest)
        self.assertFalse(page.skip(older))
        self.assertTrue(LatestPlayersPage(UI_).skip(replace(older, play=replace(older.play, recent_players=()))))

    def test_today_s_counts_shorten_to_fit(self):
        today = LatestPlayersPage.today
        self.assertEqual(today(RecentPlayer("Ann", 0, 0, 0, False)), ("not today",))
        self.assertEqual(today(RecentPlayer("Ann", 0, 1, 0, False))[0], "1 clear")
        self.assertEqual(today(RecentPlayer("Ann", 0, 0, 2, False))[0], "2 unfinished")
        self.assertEqual(today(RecentPlayer("Ann", 0, 12, 3, False)),
                         ("12 clears, 3 unfinished", "12 clears, 3 unfin.", "12 cl, 3 unfin."))
        # The longest that fits beside "59m ago" is drawn
        page, state = LatestPlayersPage(UI_), states()["busy"]
        row = RecentPlayer("Ann", state.now - 59 * 60, 12, 3, True)
        image = page.render(replace(state, play=replace(state.play, recent_players=(row,))), 1.0)
        expected = page_with(lambda im: UI_.tiny.draw(im, 1, page.TOP + 10, "12 clears, 3 unfin."))
        self.assertEqual(image.crop((0, page.TOP + 10, 80, page.TOP + 18)).tobytes(),
                         expected.crop((0, page.TOP + 10, 80, page.TOP + 18)).tobytes())

    def test_a_nickname_of_16_letters_with_marks_fits(self):
        page, state = TopPlayersPage(UI_, fade=False), states()["longest"]
        loop, _ = page._build(state)
        # Nothing touches the side edges.
        for x in (0, WIDTH - 1):
            column = loop.crop((x, 0, x + 1, loop.height))
            self.assertIsNone(column.getbbox())

    def test_stopped_goes_over_the_last_picture(self):
        from bs3d_lcd.status.pages import CHECKER, stopped
        state = states()["busy"]
        last = shots.screen(UI_, state, ServerPage(UI_), 1.0)
        bare = stopped(UI_, state.now, last, banner=False)
        banner = stopped(UI_, state.now, last)
        self.assertEqual((bare.mode, bare.size), ("1", (128, 64)))
        # What stays of the last picture is never more than every other pixel...
        from PIL import ImageChops
        self.assertIsNone(ImageChops.logical_and(bare, ImageChops.invert(CHECKER)).getbbox())
        self.assertIsNotNone(bare.getbbox())
        # ...and the banner covers the middle.
        self.assertNotEqual(bare.tobytes(), banner.tobytes())
        self.assertEqual(stopped(UI_, state.now).mode, "1")

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
