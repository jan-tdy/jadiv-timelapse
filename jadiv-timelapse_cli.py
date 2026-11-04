#!/usr/bin/env python3
"""Headless command-line version of Jadiv-Timelapse - no GUI, suitable for cron/overnight
and observatory automation.

Example:
    python3 jadiv-timelapse_cli.py ~/photos/night1 ~/videos/night1.mp4 --fps 24 --resolution fullhd --sort exif

Exit codes: 0 success, 1 rendering failed, 130 interrupted (Ctrl+C).
"""
import argparse
import os
import sys

from timelapse_core import SORT_MODES, SORT_NAME
from timelapse_render import TimelapseCancelled, TimelapseError, render_timelapse

# CLI resolution names -> labels understood by compute_target_resolution()
RESOLUTIONS = {
    "4k": "4K",
    "fullhd": "Full HD",
    "720p": "720p",
    "480p": "480p",
    "240p": "240p",
    "original": "Original",
}

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INTERRUPTED = 130


def build_parser():
    parser = argparse.ArgumentParser(
        description="Create a timelapse video from a folder of photos (headless, no GUI).",
    )
    parser.add_argument("input_folder", help="folder with the .jpg/.jpeg/.png photos")
    parser.add_argument("output", help="output video file (must end with .mp4)")
    parser.add_argument("--fps", type=int, default=24, help="frames per second (1-120, default: 24)")
    parser.add_argument(
        "--resolution", choices=sorted(RESOLUTIONS), default="fullhd",
        help="target resolution: 4k, fullhd, 720p, 480p, 240p or original (default: fullhd)",
    )
    parser.add_argument(
        "--sort", choices=SORT_MODES, default=SORT_NAME,
        help="frame order: name (default), exif (capture date, falls back to file date), mtime (file date)",
    )
    parser.add_argument("--no-watermark", action="store_true", help="do not append the closing watermark")
    parser.add_argument("-q", "--quiet", action="store_true", help="print only errors")
    return parser


def validate_args(parser, args):
    if not 1 <= args.fps <= 120:
        parser.error("--fps must be between 1 and 120")
    if not os.path.isdir(args.input_folder):
        parser.error(f"input folder does not exist: {args.input_folder}")
    if not args.output.lower().endswith(".mp4"):
        parser.error("output must be an .mp4 file")
    output_dir = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(output_dir):
        parser.error(f"output folder does not exist: {output_dir}")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)

    last_reported = [-1]

    def on_progress(percent, text):
        # Print a line roughly every 10 % (plus the final one), not for every frame
        if args.quiet:
            return
        bucket = percent // 10
        if bucket != last_reported[0] or percent >= 100:
            last_reported[0] = bucket
            print(f"[{percent:3d}%] {text}", file=sys.stderr, flush=True)

    try:
        render_timelapse(
            args.input_folder,
            args.output,
            args.fps,
            RESOLUTIONS[args.resolution],
            add_watermark=not args.no_watermark,
            sort_mode=args.sort,
            on_progress=on_progress,
        )
    except TimelapseCancelled as e:
        print(str(e), file=sys.stderr)
        return EXIT_INTERRUPTED
    except KeyboardInterrupt:
        print("Interrupted - the partial video was discarded.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except TimelapseError as e:
        print(str(e), file=sys.stderr)
        return EXIT_FAILED
    except Exception as e:  # unexpected failure (e.g. Pillow missing for --sort exif)
        print(f"An error occurred during generation:\n{e}", file=sys.stderr)
        return EXIT_FAILED

    if not args.quiet:
        print(f"Saved: {os.path.abspath(args.output)}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
