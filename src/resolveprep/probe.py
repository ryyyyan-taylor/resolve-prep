import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

# codecs Resolve already reads on Linux, so transcoding them is pure waste
INTERMEDIATE_CODECS = frozenset({"dnxhd", "prores", "cfhd", "ffv1", "v210", "rawvideo"})


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Clip:
    path: Path
    codec: str
    duration: float
    width: int
    height: int
    fps: float
    timecode: str | None
    has_audio: bool

    @property
    def already_intermediate(self):
        return self.codec in INTERMEDIATE_CODECS


def _fps(value):
    try:
        rate = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0
    return rate


def _timecode(payload):
    # Sony XAVC carries it on the rtmd data stream rather than the container
    for stream in payload.get("streams", []):
        tag = stream.get("tags", {}).get("timecode")
        if tag:
            return tag
    return payload.get("format", {}).get("tags", {}).get("timecode")


def probe(path):
    path = Path(path)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProbeError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "ffprobe failed")
    payload = json.loads(result.stdout)

    video = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise ProbeError("no video stream")

    return Clip(
        path=path,
        codec=video.get("codec_name", ""),
        duration=float(payload.get("format", {}).get("duration", 0.0)),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_fps(video.get("r_frame_rate", "0/1")),
        timecode=_timecode(payload),
        has_audio=any(s.get("codec_type") == "audio" for s in payload.get("streams", [])),
    )
