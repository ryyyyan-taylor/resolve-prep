from resolveprep.progress import QueueProgress, humanise


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_humanise_scales_with_magnitude():
    assert humanise(9) == "9s"
    assert humanise(90) == "1m30s"
    assert humanise(3700) == "1h01m"


def test_fraction_is_weighted_by_footage_not_file_count():
    progress = QueueProgress([10.0, 90.0], clock=Clock())
    progress.start(0)
    progress.advance(1.0)
    progress.ok(0)
    # one of two files done, but only a tenth of the footage
    assert progress.fraction == 0.1


def test_partial_progress_of_the_running_clip_counts():
    progress = QueueProgress([100.0], clock=Clock())
    progress.start(0)
    progress.advance(0.25)
    assert progress.fraction == 0.25


def test_eta_uses_the_encoder_speed():
    progress = QueueProgress([60.0, 60.0], clock=Clock())
    progress.start(0)
    progress.advance(0.5, speed=2.0)
    # 90s of footage left at 2x realtime
    assert progress.eta() == 45.0


def test_eta_falls_back_to_wall_clock_before_a_speed_arrives():
    clock = Clock()
    progress = QueueProgress([10.0, 10.0], clock=clock)
    progress.start(0)
    clock.advance(5.0)
    progress.ok(0)
    assert progress.eta() == 5.0


def test_skipped_footage_leaves_the_eta_budget():
    progress = QueueProgress([10.0, 90.0], clock=Clock())
    progress.skip(1)
    progress.start(0)
    progress.advance(0.0, speed=1.0)
    assert progress.remaining_duration == 10.0
    assert progress.eta() == 10.0


def test_a_fully_skipped_queue_reports_no_eta():
    progress = QueueProgress([10.0], clock=Clock())
    progress.skip(0)
    assert progress.eta() is None
    assert progress.finished == 1
