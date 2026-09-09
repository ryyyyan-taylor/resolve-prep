import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from resolveprep import logs, transcode
from resolveprep.probe import ProbeError, probe
from resolveprep.progress import QueueProgress

SUFFIX = ".mov"


class Mode(str, Enum):
    ALONGSIDE = "alongside"
    DIRECTORY = "directory"


class Status(str, Enum):
    READY = "ready"
    SKIPPED = "skipped"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Destination:
    mode: Mode = Mode.ALONGSIDE
    directory: Path | None = None

    def resolve(self, source):
        if self.mode is Mode.DIRECTORY:
            if self.directory is None:
                raise ValueError("directory mode needs a directory")
            return Path(self.directory) / (Path(source).stem + SUFFIX)
        return Path(source).with_suffix(SUFFIX)

    @property
    def root(self):
        return Path(self.directory) if self.mode is Mode.DIRECTORY else None


@dataclass
class Job:
    source: Path
    output: Path | None = None
    clip: object = None
    status: Status = Status.READY
    note: str = ""
    duration: float = 0.0
    size: int = 0
    fraction: float = 0.0
    unreadable: bool = False

    @property
    def name(self):
        return self.source.name


def inspect(paths, profile=transcode.DEFAULT_PROFILE):
    jobs = []
    for path in paths:
        source = Path(path)
        job = Job(source=source)
        try:
            clip = probe(source)
        except ProbeError as error:
            job.status, job.note, job.unreadable = Status.SKIPPED, str(error), True
        else:
            job.clip, job.duration = clip, clip.duration
            job.size = transcode.estimated_bytes(clip, profile)
        jobs.append(job)
    return jobs


# separate from inspect() so changing the destination in the window does not
# re-run ffprobe over the whole selection
def resolve(jobs, destination):
    claimed = {}
    for job in jobs:
        if job.unreadable:
            continue
        job.status, job.note, job.fraction = Status.READY, "", 0.0
        job.output = destination.resolve(job.source)
        if job.clip.already_intermediate:
            job.status, job.note = Status.SKIPPED, f"already {job.clip.codec}"
        elif job.output == job.source:
            job.status, job.note = Status.SKIPPED, "output would overwrite the source"
        elif job.output.exists():
            job.status, job.note = Status.SKIPPED, "output exists"
        elif job.output in claimed:
            job.status, job.note = Status.SKIPPED, f"name collides with {claimed[job.output]}"
        else:
            claimed[job.output] = job.source.name
    return jobs


def plan(paths, destination, profile=transcode.DEFAULT_PROFILE):
    return resolve(inspect(paths, profile), destination)


def required_bytes(jobs):
    return sum(job.size for job in jobs if job.status is Status.READY)


def free_bytes(jobs, destination):
    target = destination.root
    if target is None:
        ready = [job for job in jobs if job.status is Status.READY]
        if not ready:
            return None
        target = ready[0].output.parent
    target = Path(target)
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(target).free


def reprice(jobs, profile):
    for job in jobs:
        if job.clip is not None:
            job.size = transcode.estimated_bytes(job.clip, profile)
    return jobs


class Runner:
    def __init__(self, jobs, profile=transcode.DEFAULT_PROFILE, cancel=None, clock=time.monotonic, cpu_percent=100):
        self.jobs = jobs
        self.profile = profile
        self.cancel = cancel
        self.cpu_percent = cpu_percent
        self.progress = QueueProgress([job.duration for job in jobs], clock)
        self._log = logs.get()

    def run(self, on_start=None, on_progress=None, on_finish=None):
        for index, job in enumerate(self.jobs):
            if self.cancel is not None and self.cancel.is_set():
                break
            if job.status is Status.SKIPPED:
                self.progress.skip(index)
                if on_finish:
                    on_finish(job)
                continue

            self.progress.start(index)
            if on_start:
                on_start(job)

            def report(fraction, speed, job=job):
                job.fraction = fraction
                self.progress.advance(fraction, speed)
                if on_progress:
                    on_progress(job, fraction, speed)

            try:
                transcode.run(
                    job.clip, job.output, self.profile,
                    on_progress=report, cancel=self.cancel, cpu_percent=self.cpu_percent,
                )
            except transcode.Cancelled:
                self.progress.fail(index)
                job.status, job.note = Status.SKIPPED, "cancelled"
                if on_finish:
                    on_finish(job)
                break
            except transcode.TranscodeError as error:
                self._log.error("%s failed: %s", job.name, error)
                self.progress.fail(index)
                job.status, job.note = Status.FAILED, str(error)
            else:
                self.progress.ok(index)
                job.status = Status.DONE
            if on_finish:
                on_finish(job)
        return self.jobs
