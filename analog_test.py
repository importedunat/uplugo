# SPDX-License-Identifier: GPL-3.0-only
"""Session-only observations of raw USB stick axes, never calibration or diagnosis."""
from collections import deque
from dataclasses import dataclass, field
import math

REST_SECONDS = 5.0
MAX_GAP = .5
DIRECTION_THRESHOLD = 80.0


def percent(raw):
    return (raw-127.5)/127.5*100


@dataclass
class AxisWindow:
    count: int = 0
    sums: list = field(default_factory=lambda: [0]*4)
    low: list = field(default_factory=lambda: [255]*4)
    high: list = field(default_factory=lambda: [0]*4)
    first: float | None = None
    last: float | None = None

    def add(self, values, now):
        if self.first is None: self.first = now
        self.last = now
        self.count += 1
        for index, value in enumerate(values):
            self.sums[index] += value
            self.low[index] = min(self.low[index], value)
            self.high[index] = max(self.high[index], value)

    @property
    def seconds(self):
        return self.last-self.first if self.first is not None else 0.0

    @property
    def means(self):
        return [percent(total/self.count) for total in self.sums] if self.count else None

    def directions(self, stick):
        if not self.count: return set()
        x, y = stick*2, stick*2+1
        return {name for name, reached in (
            ('left', percent(self.low[x]) <= -DIRECTION_THRESHOLD),
            ('right', percent(self.high[x]) >= DIRECTION_THRESHOLD),
            ('up', percent(self.low[y]) <= -DIRECTION_THRESHOLD),
            ('down', percent(self.high[y]) >= DIRECTION_THRESHOLD)) if reached}


class AnalogSession:
    """Two explicit stages, continuous samples only, O(1) bounded storage.

    Times are arrival times on a monotonic clock. A gap cancels unfinished
    measurements rather than turning disconnected time into observed rest.
    Completed results remain historical until reset/close; live values clear.
    """
    def __init__(self):
        self.last_at = None
        self.values = None
        self.reset()

    def reset(self):
        self.phase = 'idle'
        self.rest = AxisWindow()
        self.travel = AxisWindow()
        self.trails = [deque(maxlen=120), deque(maxlen=120)]

    def live(self, now):
        return self.last_at is not None and 0 <= now-self.last_at < MAX_GAP

    def start_rest(self, now):
        if self.phase in ('rest', 'travel') or not self.live(now): return False
        self.reset()
        self.phase = 'rest'
        return True

    def start_travel(self, now):
        if self.phase != 'ready' or not self.live(now): return False
        self.phase = 'travel'
        return True

    def finish(self, now):
        if self.phase != 'travel' or not self.travel.count or not self.live(now): return False
        self.phase = 'done'
        return True

    def interrupt(self):
        self.last_at = self.values = None
        if self.phase in ('rest', 'ready', 'travel'):
            self.reset()
            self.phase = 'interrupted'

    def observe(self, values, now):
        if (not isinstance(values, (list, tuple)) or len(values) != 4
                or any(type(value) is not int or not 0 <= value <= 255 for value in values)
                or not isinstance(now, (int, float)) or not math.isfinite(now)):
            self.interrupt()
            return False
        if self.last_at is not None:
            if now == self.last_at: return False
            if now < self.last_at or now-self.last_at >= MAX_GAP:
                self.interrupt()
        self.last_at, self.values = now, tuple(values)
        if self.phase == 'rest':
            self.rest.add(values, now)
            if self.rest.seconds >= REST_SECONDS: self.phase = 'ready'
        elif self.phase == 'travel':
            self.travel.add(values, now)
            for stick in range(2):
                self.trails[stick].append(tuple(percent(value) for value in values[stick*2:stick*2+2]))
        return True
