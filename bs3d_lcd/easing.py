"""Easing curves: the share of a movement done, ``u`` from 0 to 1, in; the eased
share out, also from 0 to 1."""

import math


def linear(u):
    return u


def smoothstep(u):
    """Speed 0 at both ends; the acceleration jumps there."""
    return u * u * (3 - 2 * u)


def smootherstep(u):
    """Speed and acceleration 0 at both ends: a start and a stop with no jolt."""
    return u * u * u * (u * (6 * u - 15) + 10)


def sine(u):
    """Speed 0 at both ends, softer than smoothstep in the middle."""
    return (1 - math.cos(math.pi * u)) / 2


def cubic(u):
    """Slow start and stop, fast middle: the strongest of these."""
    return 4 * u ** 3 if u < 0.5 else 1 - (2 - 2 * u) ** 3 / 2


EASINGS = {
    "smootherstep": smootherstep,
    "sine": sine,
    "smoothstep": smoothstep,
    "cubic": cubic,
    "linear": linear,
}


def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u
