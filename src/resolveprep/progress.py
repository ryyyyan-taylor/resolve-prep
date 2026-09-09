import time


def humanise(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, seconds = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


# Qt-free and clock-injectable so the ETA arithmetic is testable without a
# display or a real transcode. Progress is weighted by footage duration rather
# than file count, because clip lengths here vary by 6x.
class QueueProgress:
    def __init__(self, durations, clock=time.monotonic):
        self.durations = list(durations)
        self.clock = clock
        self.total = len(self.durations)
        self.total_duration = sum(self.durations)
        self.done = 0
        self.skipped = 0
        self.failed = 0
        self.completed_duration = 0.0
        self.current_index = None
        self.current_fraction = 0.0
        self.speed = None
        self._started = clock()

    @property
    def finished(self):
        return self.done + self.skipped + self.failed

    @property
    def elapsed(self):
        return self.clock() - self._started

    @property
    def remaining_duration(self):
        current = 0.0
        if self.current_index is not None:
            current = self.durations[self.current_index] * self.current_fraction
        return max(0.0, self.total_duration - self.completed_duration - current)

    @property
    def fraction(self):
        if self.total_duration <= 0:
            return 0.0
        current = 0.0
        if self.current_index is not None:
            current = self.durations[self.current_index] * self.current_fraction
        return min(1.0, (self.completed_duration + current) / self.total_duration)

    def start(self, index):
        self.current_index = index
        self.current_fraction = 0.0

    def advance(self, fraction, speed=None):
        self.current_fraction = max(0.0, min(1.0, fraction))
        if speed:
            self.speed = speed

    def ok(self, index):
        self.done += 1
        self._retire(index)

    def skip(self, index):
        self.skipped += 1
        # skipped footage is never encoded, so it must leave the ETA budget
        self.total_duration = max(0.0, self.total_duration - self.durations[index])
        self._retire(index, credit=False)

    def fail(self, index):
        self.failed += 1
        self.total_duration = max(0.0, self.total_duration - self.durations[index])
        self._retire(index, credit=False)

    def _retire(self, index, credit=True):
        if credit:
            self.completed_duration += self.durations[index]
        self.current_index = None
        self.current_fraction = 0.0

    # ffmpeg's own speed multiplier predicts far better than wall-clock
    # averaging, especially early on when only one clip has finished
    def eta(self):
        remaining = self.remaining_duration
        if remaining <= 0:
            return None
        if self.speed:
            return remaining / self.speed
        if self.completed_duration > 0:
            return remaining * (self.elapsed / self.completed_duration)
        return None
