from pathlib import Path

from resolveprep.probe import Clip
from resolveprep.queue import Destination, Job, Mode, Status, free_bytes, required_bytes, resolve


def clip(path, codec="h264", duration=10.0):
    return Clip(
        path=Path(path), codec=codec, duration=duration, width=3840, height=2160,
        fps=30000 / 1001, timecode="00:17:30:05", has_audio=True,
    )


def job(path, codec="h264", size=100):
    source = Path(path)
    return Job(source=source, clip=clip(source, codec), duration=10.0, size=size)


def test_alongside_swaps_the_suffix():
    destination = Destination(Mode.ALONGSIDE)
    assert destination.resolve(Path("/clips/C0003.MP4")) == Path("/clips/C0003.mov")


def test_directory_mode_flattens_into_one_folder(tmp_path):
    destination = Destination(Mode.DIRECTORY, tmp_path)
    assert destination.resolve(Path("/a/b/C0003.MP4")) == tmp_path / "C0003.mov"


def test_ready_when_nothing_is_in_the_way(tmp_path):
    jobs = resolve([job(tmp_path / "C0003.MP4")], Destination(Mode.ALONGSIDE))
    assert jobs[0].status is Status.READY


def test_existing_output_is_skipped_not_overwritten(tmp_path):
    (tmp_path / "C0003.mov").write_bytes(b"already here")
    jobs = resolve([job(tmp_path / "C0003.MP4")], Destination(Mode.ALONGSIDE))
    assert jobs[0].status is Status.SKIPPED
    assert "exists" in jobs[0].note


def test_intermediate_sources_are_skipped(tmp_path):
    jobs = resolve([job(tmp_path / "C0003.mxf", codec="dnxhd")], Destination(Mode.ALONGSIDE))
    assert jobs[0].status is Status.SKIPPED
    assert "dnxhd" in jobs[0].note


def test_a_mov_source_never_overwrites_itself(tmp_path):
    source = tmp_path / "clip.mov"
    source.write_bytes(b"x")
    jobs = resolve([job(source, codec="h264")], Destination(Mode.ALONGSIDE))
    assert jobs[0].status is Status.SKIPPED
    assert "overwrite" in jobs[0].note


def test_same_basename_from_two_folders_collides_in_directory_mode(tmp_path):
    out = tmp_path / "out"
    jobs = resolve(
        [job(tmp_path / "a" / "C0003.MP4"), job(tmp_path / "b" / "C0003.MP4")],
        Destination(Mode.DIRECTORY, out),
    )
    assert jobs[0].status is Status.READY
    assert jobs[1].status is Status.SKIPPED
    assert "collides" in jobs[1].note


def test_only_ready_work_counts_towards_the_space_estimate(tmp_path):
    (tmp_path / "b.mov").write_bytes(b"done")
    jobs = resolve(
        [job(tmp_path / "a.MP4", size=500), job(tmp_path / "b.MP4", size=700)],
        Destination(Mode.ALONGSIDE),
    )
    assert required_bytes(jobs) == 500


def test_free_space_is_measured_on_the_destination(tmp_path):
    jobs = resolve([job(tmp_path / "a.MP4")], Destination(Mode.DIRECTORY, tmp_path / "not" / "made" / "yet"))
    assert free_bytes(jobs, Destination(Mode.DIRECTORY, tmp_path / "not" / "made" / "yet")) > 0


def test_reresolving_clears_a_stale_skip(tmp_path):
    (tmp_path / "C0003.mov").write_bytes(b"in the way")
    jobs = [job(tmp_path / "C0003.MP4")]
    resolve(jobs, Destination(Mode.ALONGSIDE))
    assert jobs[0].status is Status.SKIPPED
    resolve(jobs, Destination(Mode.DIRECTORY, tmp_path / "elsewhere"))
    assert jobs[0].status is Status.READY
