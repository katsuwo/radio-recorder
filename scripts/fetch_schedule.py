#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nhk_radio_recorder.nhk_api import NhkApiError, extract_programs, fetch_schedule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch an NHK radio schedule.")
    parser.add_argument("--area", default="130", help="NHK area id. Default: 130 (Tokyo)")
    parser.add_argument("--service", default="r1", help="NHK radio service id. Default: r1")
    parser.add_argument("--date", dest="target_date", help="Date in YYYY-MM-DD format")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON response")
    parser.add_argument(
        "--debug-programs",
        action="store_true",
        help="Print extracted program dictionaries for parser debugging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        payload = fetch_schedule(
            service=args.service,
            area=args.area,
            target_date=args.target_date,
        )
    except NhkApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.debug_programs:
        from nhk_radio_recorder.nhk_api import _find_program_dicts

        print(json.dumps(_find_program_dicts(payload), ensure_ascii=False, indent=2))
        return 0

    programs = extract_programs(payload)
    if not programs:
        print("No programs found. Use --raw to inspect the API response.")
        return 0

    for program in programs:
        line = f"{program.start_time} - {program.end_time}  {program.title}"
        if program.subtitle:
            line = f"{line} / {program.subtitle}"
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
