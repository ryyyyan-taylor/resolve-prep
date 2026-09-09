import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from resolveprep import logs

DEFAULT_CPU_PERCENT = 50


class TranscodeError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    label: str
    args: tuple
    # bits per pixel, used only to size the disk preflight; dnxhr_sq is measured
    # from real a6400 4K output, the rest are approximations
    bits_per_pixel: float


PROFILES = {
    "dnxhr_lb": Profile("DNxHR LB", ("-c:v", "dnxhd", "-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"), 0.90),
    "dnxhr_sq": Profile("DNxHR SQ", ("-c:v", "dnxhd", "-profile:v", "dnxhr_sq", "-pix_fmt", "yuv422p"), 2.33),
    "dnxhr_hq": Profile("DNxHR HQ", ("-c:v", "dnxhd", "-profile:v", "dnxhr_hq", "-pix_fmt", "yuv422p"), 3.50),
    "prores_lt": Profile("ProRes LT", ("-c:v", "prores_ks", "-profile:v", "1", "-pix_fmt", "yuv422p10le"), 1.30),
    "prores_422": Profile("ProRes 422", ("-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"), 1.90),
}

DEFAULT_PROFILE = "dnxhr_sq"


def estimated_bytes(clip, profile=DEFAULT_PROFILE):
    spec = PROFILES[profile]
    pixels_per_second = clip.width * clip.height * clip.fps
    return int(pixels_per_second * spec.bits_per_pixel / 8 * clip.duration)


def cores_for(percent):
    total = os.cpu_count() or 1
    return max(1, round(total * percent / 100))


# ffmpeg's own -threads is a poor throttle: 8 threads still occupied ~10.6 of 16
# cores here and ran no slower than 16. A cgroup quota caps it for real.
def wrap_for_cpu(command, percent):
    if percent >= 100 or not shutil.which("systemd-run"):
        return list(command)
    quota = max(10, int(percent) * (os.cpu_count() or 1))
    return ["systemd-run", "--user", "--scope", "--quiet", "-p", f"CPUQuota={quota}%", *command]


def build_command(clip, output, profile=DEFAULT_PROFILE):
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-progress", "pipe:1", "-nostats",
        "-i", str(clip.path),
        "-map", "0:v:0",
    ]
    if clip.has_audio:
        command += ["-map", "0:a:0"]
    if clip.timecode:
        command += ["-timecode", clip.timecode]
    command += list(PROFILES[profile].args)
    # the source is tagged iec61966-2-4 (xvYCC); Resolve reads it as bt709
    command += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    if clip.has_audio:
        command += ["-c:a", "pcm_s16le"]
    command += ["-y", str(output)]
    return command


def parse_progress(line, duration):
    key, _, value = line.strip().partition("=")
    if key == "out_time_us" and duration > 0:
        try:
            return min(1.0, int(value) / 1e6 / duration)
        except ValueError:
            return None
    return None


def parse_speed(line):
    key, _, value = line.strip().partition("=")
    if key == "speed":
        try:
            return float(value.rstrip("x"))
        except ValueError:
            return None
    return None


def run(clip, output, profile=DEFAULT_PROFILE, on_progress=None, cancel=None, cpu_percent=100):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = wrap_for_cpu(build_command(clip, output, profile), cpu_percent)
    logs.get().debug("%s", " ".join(command))

    # stderr to a file so a full pipe buffer can never deadlock the reader
    with tempfile.TemporaryFile(mode="w+") as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True)
        speed = None
        try:
            for line in process.stdout:
                if cancel is not None and cancel.is_set():
                    _terminate(process)
                    _discard(output)
                    raise Cancelled(f"cancelled {clip.path.name}")
                speed = parse_speed(line) or speed
                fraction = parse_progress(line, clip.duration)
                if fraction is not None and on_progress is not None:
                    on_progress(fraction, speed)
        finally:
            if process.stdout is not None:
                process.stdout.close()
        process.wait()
        if process.returncode != 0:
            errors.seek(0)
            detail = errors.read().strip().splitlines()
            _discard(output)
            raise TranscodeError(detail[-1] if detail else f"ffmpeg exited {process.returncode}")

    if on_progress is not None:
        on_progress(1.0, speed)
    return output


def _terminate(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _discard(output):
    # a partial .mov is worse than nothing: it would be skipped as "already done"
    try:
        output.unlink()
    except FileNotFoundError:
        pass
