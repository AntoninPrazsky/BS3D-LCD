"""The push button (#3): a short press shows the next page, a long hold switches
the alarm off.

The button sits between a GPIO (26, pin 37) and GND (pin 39). The line's
internal pull-up holds it high and a press pulls it low.
"""

import queue
import threading
import time
from datetime import timedelta

SHORT, LONG = "short", "long"


class PressTracker:
    """Tells a short press from a long hold, from the times of the edges.

    A release within ``short`` s is a short press. A hold reaches ``long`` s
    while the button is still down, and ``poll()`` reports it then; the release
    after it is nothing. A release in between is a hold given up: nothing.
    """

    def __init__(self, short=0.8, long=1.5):
        if not 0 < short <= long:
            raise ValueError(f"need 0 < short <= long, got {short} and {long}")
        self.short, self.long = short, long
        self._down = None           # when the button went down, while it is down
        self._fired = False

    def down(self, t):
        self._down, self._fired = t, False

    def up(self, t):
        """The press that ends at ``t``: SHORT or None."""
        if self._down is None:
            return None
        held, fired = t - self._down, self._fired
        self._down = None
        return SHORT if not fired and held < self.short else None

    def poll(self, now):
        """LONG once, when the hold reaches ``long`` s; otherwise None."""
        if self._down is not None and not self._fired and now - self._down >= self.long:
            self._fired = True
            return LONG
        return None

    def held(self, now):
        """How long the button has been down, while it is and the hold has not fired."""
        if self._down is None or self._fired:
            return None
        return now - self._down


class Button:
    """Edges of a push button on a header GPIO, read in a thread.

    ``edges()`` returns the ("down" | "up", t) seen since the last call; ``t``
    is the kernel's timestamp of the edge, on the clock of ``time.monotonic()``.
    """

    def __init__(self, line=26, chip=None, debounce=0.02, consumer="bs3d-lcd"):
        import gpiod
        from gpiod.line import Bias, Direction, Edge, Value

        from ..gpio import find_header_chip

        self.line = line
        chip = chip or find_header_chip()
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.BOTH,
                                      debounce_period=timedelta(seconds=debounce))
        try:
            self._request = gpiod.request_lines(chip, consumer=consumer,
                                                config={line: settings})
        except OSError as e:
            raise RuntimeError(f"GPIO{line} for the button: {e.strerror} "
                               f"(see: gpioinfo -c {chip} {line}; --button none runs "
                               "without it)") from e
        self._queue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._falling = gpiod.EdgeEvent.Type.FALLING_EDGE
        # A button already held at the start counts from now.
        if self._request.get_value(line) == Value.INACTIVE:
            self._queue.put(("down", time.monotonic()))
        self._thread = threading.Thread(target=self._read, name="button", daemon=True)
        self._thread.start()

    def _read(self):
        while not self._stop.is_set():
            if self._request.wait_edge_events(timedelta(seconds=0.5)):
                for event in self._request.read_edge_events():
                    kind = "down" if event.event_type == self._falling else "up"
                    self._queue.put((kind, event.timestamp_ns / 1e9))

    def edges(self):
        out = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        self._request.release()
