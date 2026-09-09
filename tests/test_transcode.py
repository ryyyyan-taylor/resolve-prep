from pathlib import Path

from resolveprep.probe import Clip
from resolveprep.transcode import build_command, estimated_bytes, parse_progress, parse_speed


def clip(timecode="00:17:30:05", has_audio=True):
    return Clip(
        path=Path("/clips/C0003.MP4"), codec="h264", duration=11.015, width=3840, height=2160,
        fps=30000 / 1001, timecode=timecode, has_audio=has_audio,
    )


def test_command_carries_the_settings_the_footage_needs():
    command = build_command(clip(), Path("/out/C0003.mov"))
    joined = " ".join(command)
    assert "-map 0:v:0" in joined
    assert "-map 0:a:0" in joined
    assert "-timecode 00:17:30:05" in joined
    assert "-profile:v dnxhr_sq" in joined
    assert "-pix_fmt yuv422p" in joined
    # big-endian source PCM must be rewritten, never copied
    assert "-c:a pcm_s16le" in joined
    assert "-c:a copy" not in joined
    assert "-colorspace bt709" in joined


def test_the_rtmd_data_stream_is_never_mapped():
    command = build_command(clip(), Path("/out/C0003.mov"))
    assert "0:d:0" not in " ".join(command)
    assert " ".join(command).count("-map") == 2


def test_timecode_is_omitted_when_the_source_has_none():
    command = build_command(clip(timecode=None), Path("/out/x.mov"))
    assert "-timecode" not in command


def test_silent_sources_get_no_audio_flags():
    command = build_command(clip(has_audio=False), Path("/out/x.mov"))
    joined = " ".join(command)
    assert "-map 0:a:0" not in joined
    assert "-c:a" not in joined


def test_progress_is_reported_against_the_probed_duration():
    assert parse_progress("out_time_us=5507500", 11.015) == 0.5
    assert parse_progress("frame=100", 11.015) is None


def test_progress_never_exceeds_one():
    assert parse_progress("out_time_us=99999999", 11.015) == 1.0


def test_speed_parses_the_trailing_x():
    assert parse_speed("speed=2.29x") == 2.29
    assert parse_speed("speed=N/A") is None


def test_size_estimate_lands_near_the_measured_output():
    # the real DNxHR SQ encode of this clip was 760 MB
    estimate = estimated_bytes(clip())
    assert 0.85 < estimate / 797_000_000 < 1.15
