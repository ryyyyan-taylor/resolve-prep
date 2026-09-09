import os

from resolveprep import transcode
from resolveprep.probe import Clip
from resolveprep.queue import Job, reprice
from pathlib import Path


def clip(width=3840, height=2160):
    return Clip(path=Path("/c/x.MP4"), codec="h264", duration=10.0, width=width, height=height,
                fps=30.0, timecode=None, has_audio=True)


def test_full_speed_runs_ffmpeg_unwrapped():
    assert transcode.wrap_for_cpu(["ffmpeg", "-i", "x"], 100) == ["ffmpeg", "-i", "x"]


def test_throttling_wraps_in_a_cgroup_scope():
    wrapped = transcode.wrap_for_cpu(["ffmpeg"], 50)
    if not transcode.shutil.which("systemd-run"):
        assert wrapped == ["ffmpeg"]
        return
    assert wrapped[0] == "systemd-run"
    assert wrapped[-1] == "ffmpeg"
    # CPUQuota counts 100% per core, so half of an N-core box is N*50%
    assert f"CPUQuota={50 * os.cpu_count()}%" in wrapped


def test_cores_scale_with_the_percentage():
    total = os.cpu_count()
    assert transcode.cores_for(100) == total
    assert transcode.cores_for(50) == round(total * 0.5)
    # never zero, however low the slider goes
    assert transcode.cores_for(1) >= 1


def test_quality_changes_the_size_estimate():
    lb = transcode.estimated_bytes(clip(), "dnxhr_lb")
    sq = transcode.estimated_bytes(clip(), "dnxhr_sq")
    hq = transcode.estimated_bytes(clip(), "dnxhr_hq")
    assert lb < sq < hq


def test_estimate_scales_with_resolution():
    assert transcode.estimated_bytes(clip(1920, 1080)) < transcode.estimated_bytes(clip(3840, 2160))


def test_reprice_updates_jobs_in_place():
    job = Job(source=Path("/c/x.MP4"), clip=clip(), size=0)
    reprice([job], "dnxhr_hq")
    assert job.size == transcode.estimated_bytes(clip(), "dnxhr_hq")


def test_reprice_ignores_unreadable_jobs():
    job = Job(source=Path("/c/bad.MP4"), clip=None, size=0, unreadable=True)
    reprice([job], "dnxhr_hq")
    assert job.size == 0
