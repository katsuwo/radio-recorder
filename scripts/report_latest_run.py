#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
from datetime import datetime, timedelta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report recent recording and transcription outputs.")
    parser.add_argument("--recordings-dir", default="recordings")
    parser.add_argument("--transcripts-dir", default="transcripts")
    parser.add_argument("--hours", type=int, default=24)
    return parser.parse_args()


def recent_files(root: pathlib.Path, since: datetime) -> list[pathlib.Path]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*") if path.is_file()]
    return sorted(
        [path for path in files if datetime.fromtimestamp(path.stat().st_mtime) >= since],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def main() -> int:
    args = parse_args()
    since = datetime.now() - timedelta(hours=args.hours)
    recordings = recent_files(pathlib.Path(args.recordings_dir), since)
    transcripts = recent_files(pathlib.Path(args.transcripts_dir), since)

    print(f"Recent recordings ({len(recordings)})")
    for path in recordings[:20]:
        print(path)

    print(f"Recent transcripts ({len(transcripts)})")
    for path in transcripts[:20]:
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
