"""The push's easing, the siren's and the knock's level curves and the button's presses
(#2, #3, #8)."""

import unittest

from bs3d_lcd.easing import EASINGS, smootherstep
from bs3d_lcd.status.button import LONG, SHORT, PressTracker
from bs3d_lcd.status.siren import Knock, Siren

STEPS = [i / 1000 for i in range(1001)]


class EasingTest(unittest.TestCase):
    def test_ends_and_never_backwards(self):
        for name, ease in EASINGS.items():
            with self.subTest(name):
                self.assertAlmostEqual(ease(0.0), 0.0)
                self.assertAlmostEqual(ease(1.0), 1.0)
                values = [ease(u) for u in STEPS]
                self.assertTrue(all(b >= a - 1e-12 for a, b in zip(values, values[1:])))

    def test_eased_ones_start_and_stop_without_speed(self):
        h = 1e-4
        for name, ease in EASINGS.items():
            if name == "linear":
                continue
            with self.subTest(name):
                self.assertLess(ease(h) / h, 0.01)
                self.assertLess((1 - ease(1 - h)) / h, 0.01)

    def test_smootherstep_starts_without_a_jolt_in_acceleration(self):
        h = 1e-3
        acceleration = (smootherstep(2 * h) - 2 * smootherstep(h) + smootherstep(0)) / h ** 2
        self.assertLess(abs(acceleration), 0.1)

    def test_the_two_pages_always_touch(self):
        # The old page at -x and the new one at W - x: no gap, no overlap.
        width = 128
        for u in STEPS:
            x = round(width * smootherstep(u))
            self.assertEqual((width - x) - (-x), width)

    def test_whole_pixels_are_enough_at_200_fps(self):
        # The fastest frame of the default 1 s push moves under 2 px.
        frames = round(1.0 * 200)
        xs = [128 * smootherstep(k / frames) for k in range(frames + 1)]
        self.assertLess(max(b - a for a, b in zip(xs, xs[1:])), 2.0)


class SirenTest(unittest.TestCase):
    def levels(self, siren, start, end, step=0.005):
        n = round((end - start) / step)
        return [siren.level(start + k * step) for k in range(n + 1)]

    def test_stays_between_low_and_high(self):
        for shape in ("siren", "sine"):
            siren = Siren(0.85, 1.15, 1.0, shape)
            siren.start(0.0)
            levels = self.levels(siren, 0.0, 5.0)
            self.assertGreaterEqual(min(levels), 0.85 - 1e-9)
            self.assertLessEqual(max(levels), 1.15 + 1e-9)
            self.assertLess(min(levels), 0.86)
            self.assertGreater(max(levels), 1.14)

    def test_starts_and_ends_at_one_without_a_jump(self):
        siren = Siren()
        self.assertEqual(siren.level(0.0), 1.0)
        siren.start(1.0)
        self.assertAlmostEqual(siren.level(1.0), 1.0)
        siren.stop(3.37)
        levels = self.levels(siren, 0.0, 5.0)
        self.assertLess(max(abs(b - a) for a, b in zip(levels, levels[1:])), 0.02)
        self.assertEqual(siren.level(5.0), 1.0)

    def test_quick_rise_slow_fall(self):
        siren = Siren(0.85, 1.15, 1.0, "siren", rise=0.3)
        self.assertAlmostEqual(siren.wave(0.0), 0.85)
        self.assertAlmostEqual(siren.wave(0.3), 1.15)
        self.assertGreater(siren.wave(0.55), 1.0)      # still on the way down

    def test_restart_while_fading_goes_on_smoothly(self):
        siren = Siren()
        siren.start(0.0)
        siren.stop(2.0)
        siren.start(2.2)
        levels = self.levels(siren, 1.5, 3.0)
        self.assertLess(max(abs(b - a) for a, b in zip(levels, levels[1:])), 0.02)

    def test_refuses_a_swing_that_misses_one(self):
        with self.assertRaises(ValueError):
            Siren(1.05, 1.2)


class KnockTest(unittest.TestCase):
    def levels(self, knock, start, end, step=0.001):
        n = round((end - start) / step)
        return [knock.level(start + k * step) for k in range(n + 1)]

    @staticmethod
    def dips(levels):
        return sum(1 for a, b in zip(levels, levels[1:]) if a == 1.0 and b < 1.0)

    def test_two_dips_then_still_every_period(self):
        knock = Knock(0.9, dip=0.25, gap=0.15, dips=2, period=4.0)
        self.assertEqual(knock.level(0.0), 1.0)
        knock.start(0.0)
        levels = self.levels(knock, 0.0, 12.0)
        self.assertEqual(self.dips([1.0] + levels), 6)
        self.assertAlmostEqual(min(levels), 0.9, places=3)
        self.assertEqual(max(levels), 1.0)
        self.assertEqual(set(self.levels(knock, 0.65, 3.99)), {1.0})     # still after the second dip
        self.assertLess(knock.level(4.125), 0.95)                        # and again

    def test_never_jumps_and_a_dip_under_way_is_finished(self):
        knock = Knock()
        knock.start(1.0)
        knock.stop(1.1)                     # in the middle of the first dip
        levels = self.levels(knock, 0.0, 3.0)
        self.assertLess(max(abs(b - a) for a, b in zip(levels, levels[1:])), 0.01)
        self.assertLess(knock.level(1.2), 1.0)
        self.assertEqual(knock.level(1.26), 1.0)
        self.assertEqual(set(self.levels(knock, 1.26, 6.0)), {1.0})    # no second dip

    def test_refuses_what_is_no_knock(self):
        with self.assertRaises(ValueError):
            Knock(1.1)
        with self.assertRaises(ValueError):
            Knock(dip=1.0, gap=1.0, dips=3, period=4.0)


class PressTrackerTest(unittest.TestCase):
    def test_short_press(self):
        tracker = PressTracker(0.8, 1.5)
        tracker.down(10.0)
        self.assertIsNone(tracker.poll(10.3))
        self.assertEqual(tracker.up(10.3), SHORT)

    def test_long_hold_fires_while_held_and_the_release_is_nothing(self):
        tracker = PressTracker(0.8, 1.5)
        tracker.down(10.0)
        self.assertIsNone(tracker.poll(11.49))
        self.assertAlmostEqual(tracker.held(11.2), 1.2)
        self.assertEqual(tracker.poll(11.5), LONG)
        self.assertIsNone(tracker.poll(11.6))           # once only
        self.assertIsNone(tracker.held(11.6))
        self.assertIsNone(tracker.up(13.0))

    def test_a_hold_given_up_is_nothing(self):
        tracker = PressTracker(0.8, 1.5)
        tracker.down(10.0)
        self.assertIsNone(tracker.poll(11.0))
        self.assertIsNone(tracker.up(11.2))

    def test_a_release_without_a_press_is_nothing(self):
        self.assertIsNone(PressTracker().up(1.0))

    def test_quick_presses_each_count(self):
        # The owner's gpiomon test: presses 0.3 s apart.
        tracker = PressTracker()
        presses = 0
        for k in range(5):
            tracker.down(k * 0.35)
            presses += tracker.up(k * 0.35 + 0.1) == SHORT
        self.assertEqual(presses, 5)


if __name__ == "__main__":
    unittest.main()
