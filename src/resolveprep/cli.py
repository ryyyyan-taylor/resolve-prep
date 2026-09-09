import argparse
from pathlib import Path

from resolveprep import config, logs, transcode
from resolveprep.progress import humanise
from resolveprep.queue import Destination, Mode, Runner, Status, free_bytes, plan, required_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(prog="resolve-prep", description="Transcode camera clips to DNxHR for DaVinci Resolve")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="transcode clips without a window")
    run.add_argument("clips", type=Path, nargs="+")
    run.add_argument("-o", "--output-dir", type=Path, default=None, help="write here instead of beside each clip")
    run.add_argument("-p", "--profile", choices=sorted(transcode.PROFILES), default=None)
    run.add_argument("-c", "--cpu", type=int, default=None, metavar="PERCENT",
                     help="share of the CPU to use, 10-100 (default 50)")
    run.set_defaults(handler=_run)

    gui = subcommands.add_parser("ui", help="open the transcode window")
    gui.add_argument("clips", type=Path, nargs="*")
    gui.set_defaults(handler=_ui)

    args = parser.parse_args(argv)
    logs.configure()
    return args.handler(args)


def _run(args):
    settings = config.load()
    profile = args.profile or settings["profile"]
    cpu_percent = args.cpu if args.cpu is not None else settings["cpu_percent"]
    cpu_percent = max(10, min(100, cpu_percent))
    destination = (
        Destination(mode=Mode.DIRECTORY, directory=args.output_dir)
        if args.output_dir
        else Destination(mode=Mode.ALONGSIDE)
    )

    jobs = plan(args.clips, destination, profile)
    needed = required_bytes(jobs)
    free = free_bytes(jobs, destination)
    if free is not None and needed > free:
        print(f"not enough space: need ~{needed / 1e9:.1f} GB, {free / 1e9:.1f} GB free")
        return 1

    total = sum(1 for job in jobs if job.status is Status.READY)
    print(f"{total} to transcode, ~{needed / 1e9:.1f} GB, {transcode.PROFILES[profile].label}, "
          f"{cpu_percent}% CPU (~{transcode.cores_for(cpu_percent)} cores)")

    runner = Runner(jobs, profile, cpu_percent=cpu_percent)

    def finished(job):
        eta = runner.progress.eta()
        tail = f"  eta {humanise(eta)}" if eta else ""
        print(f"[{runner.progress.finished}/{len(jobs)}] {job.name}  {job.status.value} {job.note}{tail}")

    runner.run(on_finish=finished)
    failed = sum(1 for job in jobs if job.status is Status.FAILED)
    print(f"done: {runner.progress.done} written, {runner.progress.skipped} skipped, {failed} failed")
    return 1 if failed else 0


# imported here so `run` keeps working without the optional ui extra
def _ui(args):
    from resolveprep.ui.window import launch

    return launch(args.clips)
