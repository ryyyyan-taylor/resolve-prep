import threading

from PySide6.QtCore import QObject, Signal, Slot

from resolveprep import logs
from resolveprep.queue import Runner


class TranscodeWorker(QObject):
    started = Signal(object)
    progressed = Signal(object, float, object)
    completed = Signal(object)
    tick = Signal(float, object)
    done = Signal()

    def __init__(self):
        super().__init__()
        self.cancel = threading.Event()
        self._log = logs.get()

    @Slot(object, str)
    def run(self, jobs, profile):
        self.cancel.clear()
        runner = Runner(jobs, profile, cancel=self.cancel)

        def progressed(job, fraction, speed):
            self.progressed.emit(job, fraction, speed)
            self.tick.emit(runner.progress.fraction, runner.progress.eta())

        def completed(job):
            self.completed.emit(job)
            self.tick.emit(runner.progress.fraction, runner.progress.eta())

        try:
            runner.run(on_start=self.started.emit, on_progress=progressed, on_finish=completed)
        except Exception as error:
            self._log.exception("queue aborted: %s", error)
        self.done.emit()

    @Slot()
    def stop(self):
        self.cancel.set()
