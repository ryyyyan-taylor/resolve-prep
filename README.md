# resolve-prep

Transcode camera clips to DNxHR so DaVinci Resolve on Linux can import them.

The free build of Resolve ships no H.264 decoder on Linux, so footage from most
cameras imports offline (`Codec (avc1) not Found in Repository` in the Resolve
log). This converts clips to a DNxHR MOV that Resolve reads natively.

Select clips in your file manager, choose **Open With → Resolve Prep**, pick a
destination and press Start. Originals are never modified or deleted.

## Usage

    resolve-prep ui  [clips...]           # window with queue and progress
    resolve-prep run [clips...]           # headless, writes beside each clip
    resolve-prep run -o /path [clips...]  # headless, writes to one directory
    resolve-prep run -p dnxhr_hq [clips]  # LB / SQ / HQ, or ProRes LT / 422
    resolve-prep run -c 100 [clips...]    # share of CPU to use, default 50

## Processing speed

Transcoding will otherwise take every core it can get. The speed control caps it
with a cgroup quota, defaulting to half the machine so the box stays usable.
On a 16-thread CPU, 50% measured ~6.7 cores at 1.5x realtime against ~11.1
cores at 2.4x unlimited.

## What it preserves

- Source timecode, including the Sony XAVC `rtmd` track that ffprobe hides
- Audio, re-encoded to little-endian PCM (Sony records big-endian, which MOV
  will not carry)
- bt709 colour tagging in place of the camera's xvYCC tags

## Install

    uv tool install --editable .
    ln -sf "$PWD/packaging/resolve-prep.desktop" ~/.local/share/applications/
    update-desktop-database ~/.local/share/applications
