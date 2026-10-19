"""The alarm: the whole panel pulses by swinging its drive voltage V0 (#3)."""

import math

from ..easing import clamp01, smoothstep

SHAPES = ("siren", "sine")


class Siren:
    """The V0 level while an error stands: it swings between ``low`` and ``high``.

    The ``siren`` shape rises quickly, in ``rise`` of the period, and falls
    slowly in the rest, both eased; ``sine`` is the plain alternative. The
    swing fades in over ``attack`` s when the siren starts and out over
    ``release`` s when it stops, so the level leaves 1.0 and comes back to it
    without a jump. ``level(now)`` is 1.0 while it is silent.
    """

    def __init__(self, low=0.85, high=1.15, period=1.5, shape="siren", rise=0.3,
                 attack=0.3, release=0.6):
        if not low <= 1.0 <= high:
            raise ValueError(f"the siren must swing around 1.0, got {low}-{high}")
        if shape not in SHAPES:
            raise ValueError(f"shape must be one of {SHAPES}, got {shape!r}")
        self.low, self.high, self.period, self.shape, self.rise = low, high, period, shape, rise
        self.attack, self.release = attack, release
        self.on = False
        self._t0 = 0.0              # when the wave started
        self._from, self._at = 0.0, 0.0

    def wave(self, t):
        """The swing ``t`` s after the wave started, from ``low`` at t = 0."""
        p = (t / self.period) % 1.0
        if self.shape == "sine":
            k = (1 - math.cos(2 * math.pi * p)) / 2
        elif p < self.rise:
            k = smoothstep(p / self.rise)
        else:
            k = 1 - smoothstep((p - self.rise) / (1 - self.rise))
        return self.low + (self.high - self.low) * k

    def envelope(self, now):
        """How much of the swing is applied, 0 to 1."""
        if self.on:
            return self._from + (1 - self._from) * smoothstep(clamp01((now - self._at) / self.attack))
        return self._from * (1 - smoothstep(clamp01((now - self._at) / self.release)))

    def start(self, now):
        if self.on:
            return
        envelope = self.envelope(now)
        if envelope == 0:
            self._t0 = now          # a fresh start; otherwise the wave goes on
        self.on, self._from, self._at = True, envelope, now

    def stop(self, now):
        if not self.on:
            return
        self._from, self._at = self.envelope(now), now
        self.on = False

    def level(self, now):
        envelope = self.envelope(now)
        if envelope == 0:
            return 1.0
        return 1.0 + envelope * (self.wave(now - self._t0) - 1.0)
