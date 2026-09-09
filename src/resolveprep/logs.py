import logging
import os
from pathlib import Path

LOGGER_NAME = "resolveprep"
FORMAT = "%(asctime)s %(levelname)-5s %(message)s"
TIMESTAMP = "%H:%M:%S"


def log_path():
    state = os.environ.get("XDG_STATE_HOME")
    root = Path(state) if state else Path.home() / ".local" / "state"
    return root / "resolve-prep" / "session.log"


def configure(level=logging.DEBUG):
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # truncate per run: the log is for inspecting one sitting, not an archive
    handler = logging.FileHandler(path, mode="w")
    handler.setFormatter(logging.Formatter(FORMAT, TIMESTAMP))
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter(FORMAT, TIMESTAMP))
    logger.addHandler(stream)
    logger.info("logging to %s", path)
    return logger


def get():
    return logging.getLogger(LOGGER_NAME)
