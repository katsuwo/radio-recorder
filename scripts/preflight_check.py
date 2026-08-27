#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nhk_radio_recorder.nhk_api import NhkApiError
from nhk_radio_recorder.recording import (
    build_targets_for_day,
    default_stream_urls,
    parse_services,
    resolve_ffmpeg_bin,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run operational checks for radio-recorder.")
    parser.add_argument("--area", default=os.environ.get("AREA", "130"))
    parser.add_argument("--services", default=os.environ.get("SERVICES", "r1,r3"))
    parser.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", str(PROJECT_ROOT / "recordings")))
    return parser.parse_args()


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def main() -> int:
    args = parse_args()
    services = parse_services(args.services)
    output_dir = pathlib.Path(args.output_dir)
    today = datetime.now().date()

    if not os.environ.get("NHK_API_KEY"):
        return fail("NHK_API_KEY is missing")

    try:
        ffmpeg_path = resolve_ffmpeg_bin()
    except FileNotFoundError as exc:
        return fail(str(exc))

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        stream_urls = default_stream_urls(services, area=args.area)
    except Exception as exc:
        return fail(f"stream URL resolution failed: {exc}")

    try:
        targets = build_targets_for_day(area=args.area, services=services, target_date=today)
    except NhkApiError as exc:
        return fail(f"NHK schedule fetch failed: {exc}")

    print(f"OK: ffmpeg={ffmpeg_path}")
    print(f"OK: output_dir={output_dir}")
    print(f"OK: services={','.join(services)} area={args.area}")
    print(f"OK: stream_urls={stream_urls}")
    print(f"OK: targets_today={len(targets)}")
    for target in targets[:10]:
        print(f"  {target.program.service} {target.program.start_at.isoformat()} {target.program.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
