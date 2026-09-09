import os
import tomllib
from pathlib import Path

import tomli_w

from resolveprep import transcode
from resolveprep.queue import Destination, Mode

DEFAULTS = {
    "mode": Mode.ALONGSIDE.value,
    "directory": "",
    "profile": transcode.DEFAULT_PROFILE,
    "cpu_percent": transcode.DEFAULT_CPU_PERCENT,
}


def config_path():
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "resolve-prep" / "config.toml"


def load(path=None):
    path = Path(path) if path else config_path()
    values = dict(DEFAULTS)
    try:
        with path.open("rb") as handle:
            values.update(tomllib.load(handle))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        pass
    if values.get("profile") not in transcode.PROFILES:
        values["profile"] = transcode.DEFAULT_PROFILE
    values["cpu_percent"] = _percent(values.get("cpu_percent"))
    return values


def _percent(value):
    try:
        return max(10, min(100, int(value)))
    except (TypeError, ValueError):
        return transcode.DEFAULT_CPU_PERCENT


def save(values, path=None):
    path = Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps({k: values.get(k, v) for k, v in DEFAULTS.items()}).encode())


def destination(values):
    try:
        mode = Mode(values.get("mode", Mode.ALONGSIDE.value))
    except ValueError:
        mode = Mode.ALONGSIDE
    directory = values.get("directory") or None
    if mode is Mode.DIRECTORY and not directory:
        mode = Mode.ALONGSIDE
    return Destination(mode=mode, directory=Path(directory) if directory else None)
