from pathlib import Path

from resolveprep import config
from resolveprep.queue import Mode


def test_defaults_when_no_file_exists(tmp_path):
    values = config.load(tmp_path / "missing.toml")
    assert values["mode"] == Mode.ALONGSIDE.value
    assert values["profile"] == "dnxhr_sq"


def test_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    config.save({"mode": "directory", "directory": "/tmp/out", "profile": "prores_lt"}, path)
    values = config.load(path)
    assert values["mode"] == "directory"
    assert config.destination(values).directory == Path("/tmp/out")


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not toml {{{")
    assert config.load(path)["profile"] == "dnxhr_sq"


def test_unknown_profile_is_replaced(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('profile = "h264_nonsense"')
    assert config.load(path)["profile"] == "dnxhr_sq"


def test_directory_mode_without_a_directory_degrades_to_alongside():
    destination = config.destination({"mode": "directory", "directory": ""})
    assert destination.mode is Mode.ALONGSIDE
