from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import Request, urlopen

from nhk_radio_recorder.nhk_api import Program, extract_programs, fetch_schedule


SUPPORTED_SERVICES = ("r1", "r3")
RADIRU_CONFIG_URL = "https://www.nhk.or.jp/radio/config/config_web.xml"
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "recording_rules.json"
PROJECT_FFMPEG_PATH = Path(__file__).resolve().parents[1] / "tools" / "ffmpeg" / "ffmpeg"
RULE_REFRESH_INTERVAL_SECONDS = 30
DEFAULT_FFMPEG_CANDIDATES = (
    str(PROJECT_FFMPEG_PATH),
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/snap/bin/ffmpeg",
)


@dataclass(frozen=True)
class RecordingTarget:
    category: str
    folder_name: str
    program: Program

    @property
    def duration_seconds(self) -> int:
        delta = self.program.end_at - self.program.start_at
        return max(1, int(delta.total_seconds()))

    @property
    def service_folder(self) -> str:
        return sanitize_name(self.program.service or "unknown")

    @property
    def series_folder(self) -> str:
        return sanitize_name(self.program.display_name)

    def output_path(self, root_dir: Path) -> Path:
        start_label = self.program.start_at.strftime("%Y%m%d_%H%M")
        file_name = sanitize_name(f"{start_label}_{self.program.title}") + ".m4a"
        return root_dir / self.service_folder / self.folder_name / self.series_folder / file_name


@dataclass(frozen=True)
class MatchRule:
    category: str
    folder_name: str
    match: tuple[str, ...]


@dataclass(frozen=True)
class RecordingRules:
    include: tuple[MatchRule, ...]
    exclude: tuple[tuple[str, ...], ...] = ()


def parse_services(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return SUPPORTED_SERVICES

    services = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    unknown = [service for service in services if service not in SUPPORTED_SERVICES]
    if unknown:
        raise ValueError(f"Unsupported service ids: {', '.join(unknown)}")
    return services or SUPPORTED_SERVICES


def fetch_programs_for_day(*, area: str, services: Iterable[str], target_date: date) -> list[Program]:
    programs_by_id: dict[str, Program] = {}
    today = datetime.now().date()

    for service in services:
        days_to_fetch = [target_date]
        previous_day = target_date - timedelta(days=1)
        # NHK's v3 schedule API only serves data from today forward, so avoid
        # querying a past date that would hard-fail with HTTP 400.
        if previous_day >= today:
            days_to_fetch.insert(0, previous_day)
        for day in days_to_fetch:
            payload = fetch_schedule(service=service, area=area, target_date=day.isoformat())
            for program in extract_programs(payload):
                if program.start_at.date() != target_date:
                    continue
                key = program.program_id or f"{program.service}:{program.start_time}:{program.title}"
                programs_by_id[key] = program

    return sorted(programs_by_id.values(), key=lambda program: program.start_at)


def classify_program(program: Program, rules: RecordingRules | None = None) -> RecordingTarget | None:
    rules = rules or load_recording_rules()
    text_parts = [program.title, program.subtitle or "", program.series_name or "", " ".join(program.genres)]
    haystack = " ".join(text_parts)

    if any(any(keyword in haystack for keyword in keywords) for keywords in rules.exclude):
        return None

    for rule in rules.include:
        if any(keyword in haystack for keyword in rule.match):
            return RecordingTarget(rule.category, rule.folder_name, program)

    return None


def select_targets(programs: Iterable[Program], rules: RecordingRules | None = None) -> list[RecordingTarget]:
    rules = rules or load_recording_rules()
    targets: list[RecordingTarget] = []
    seen: set[tuple[str, str, str]] = set()
    for program in programs:
        target = classify_program(program, rules)
        if target is None:
            continue
        key = (target.program.service, target.category, target.program.program_id or target.program.start_time)
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
    return sorted(targets, key=lambda target: target.program.start_at)


def sanitize_name(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:120] or "untitled"


def resolve_ffmpeg_bin() -> str:
    configured = os.environ.get("FFMPEG_BIN", "").strip()
    if configured:
        if Path(configured).is_file():
            return configured
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise FileNotFoundError(f"Configured FFMPEG_BIN was not found: {configured}")

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    for candidate in DEFAULT_FFMPEG_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    raise FileNotFoundError("ffmpeg was not found in PATH and FFMPEG_BIN is not set.")


def load_recording_rules(path: str | Path | None = None) -> RecordingRules:
    rules_path = Path(path) if path else DEFAULT_RULES_PATH
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    include = tuple(_parse_include_rule(item) for item in payload.get("include", []))
    if not include:
        raise ValueError(f"No include rules found in {rules_path}")

    exclude = tuple(_parse_match_terms(item) for item in payload.get("exclude", []))
    return RecordingRules(include=include, exclude=exclude)


def _parse_include_rule(item: object) -> MatchRule:
    if not isinstance(item, dict):
        raise ValueError("Include rule must be an object.")
    category = str(item.get("category", "")).strip()
    folder_name = str(item.get("folder_name", "")).strip()
    match = _parse_match_terms(item)
    if not category or not folder_name:
        raise ValueError("Include rule requires category and folder_name.")
    return MatchRule(category=category, folder_name=folder_name, match=match)


def _parse_match_terms(item: object) -> tuple[str, ...]:
    if not isinstance(item, dict):
        raise ValueError("Rule must be an object.")
    raw_match = item.get("match", [])
    if not isinstance(raw_match, list):
        raise ValueError("Rule match must be a list.")
    terms = tuple(str(value).strip() for value in raw_match if str(value).strip())
    if not terms:
        raise ValueError("Rule match must contain at least one term.")
    return terms


def format_target(target: RecordingTarget) -> str:
    start_label = target.program.start_at.strftime("%H:%M")
    end_label = target.program.end_at.strftime("%H:%M")
    return f"[{target.program.service}:{target.category}] {start_label}-{end_label} {target.program.title}"


def default_stream_url(service: str) -> str | None:
    return os.environ.get(f"NHK_{service.upper()}_STREAM_URL")


def fetch_stream_urls_for_area(area: str, timeout: float = 20.0) -> dict[str, str]:
    request = Request(
        RADIRU_CONFIG_URL,
        headers={
            "Accept": "application/xml,text/xml",
            "User-Agent": "radio-recorder/0.1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    area_key = area.strip()
    for node in root.findall(".//stream_url/data"):
        if (node.findtext("areakey") or "").strip() != area_key:
            continue
        r1hls = (node.findtext("r1hls") or "").strip()
        fmhls = (node.findtext("fmhls") or "").strip()
        resolved = {}
        if r1hls:
            resolved["r1"] = r1hls
        if fmhls:
            resolved["r3"] = fmhls
        if resolved:
            return resolved
    raise ValueError(f"No stream URLs found for area {area_key}")


def default_stream_urls(services: Iterable[str], *, area: str) -> dict[str, str]:
    dynamic_urls: dict[str, str] = {}
    try:
        dynamic_urls = fetch_stream_urls_for_area(area)
    except Exception:
        dynamic_urls = {}

    missing: list[str] = []
    resolved: dict[str, str] = {}
    for service in services:
        stream_url = dynamic_urls.get(service) or default_stream_url(service)
        if not stream_url:
            missing.append(service)
            continue
        resolved[service] = stream_url
    if missing:
        missing_labels = ", ".join(f"{service} (or NHK_{service.upper()}_STREAM_URL)" for service in missing)
        raise ValueError(f"Missing stream URLs: {missing_labels}")
    return resolved


def run_recording_schedule(
    *,
    targets: Iterable[RecordingTarget],
    stream_urls: dict[str, str],
    output_dir: Path,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> None:
    now_fn = now_fn or datetime.now
    sleep_fn = sleep_fn or time.sleep

    for target in targets:
        start_at = target.program.start_at
        end_at = target.program.end_at
        now = now_fn().astimezone(start_at.tzinfo)
        print(f"Recording candidate: {format_target(target)}")

        if now >= end_at:
            print(f"Skipping ended program: {format_target(target)}")
            continue

        if now < start_at:
            wait_seconds = (start_at - now).total_seconds()
            print(
                f"Waiting {int(wait_seconds)} seconds until "
                f"{start_at.isoformat()} for {format_target(target)}"
            )
            sleep_fn(wait_seconds)
            now = now_fn().astimezone(start_at.tzinfo)

        stream_url = stream_urls.get(target.program.service)
        if not stream_url:
            raise ValueError(f"Missing stream URL for service {target.program.service}")

        duration_seconds = max(1, int((end_at - now).total_seconds()))
        output_path = target.output_path(output_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = resolve_ffmpeg_bin()

        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            stream_url,
            "-vn",
            "-acodec",
            "copy",
            "-t",
            str(duration_seconds),
            str(output_path),
        ]
        print(f"Recording to {output_path} for {duration_seconds} seconds")
        subprocess.run(command, check=True)
        print(f"Finished recording: {output_path}")


def run_live_recording_schedule(
    *,
    area: str,
    services: Iterable[str],
    target_date: date,
    stream_urls: dict[str, str],
    output_dir: Path,
    rules_path: str | Path | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    refresh_interval_seconds: int = RULE_REFRESH_INTERVAL_SECONDS,
    fetch_targets_fn: Callable[..., list[RecordingTarget]] | None = None,
) -> None:
    now_fn = now_fn or datetime.now
    sleep_fn = sleep_fn or time.sleep
    fetch_targets_fn = fetch_targets_fn or build_targets_for_day
    seen: set[tuple[str, str, str]] = set()

    while True:
        now = now_fn()
        targets = fetch_targets_fn(
            area=area,
            services=services,
            target_date=target_date,
            rules_path=rules_path,
        )
        pending = _pending_targets(targets=targets, seen=seen, now=now)
        if not pending:
            print(f"No pending matching programs remain for {target_date.isoformat()}.")
            return

        next_target = pending[0]
        start_at = next_target.program.start_at
        end_at = next_target.program.end_at
        now_local = now.astimezone(start_at.tzinfo)

        if now_local < start_at:
            wait_seconds = min(
                (start_at - now_local).total_seconds(),
                float(max(1, refresh_interval_seconds)),
            )
            print(
                f"Waiting {int(wait_seconds)} seconds until refresh before "
                f"{format_target(next_target)}"
            )
            sleep_fn(wait_seconds)
            continue

        if now_local >= end_at:
            seen.add(target_identity(next_target))
            continue

        print(f"Recording candidate: {format_target(next_target)}")
        _record_target(
            target=next_target,
            stream_urls=stream_urls,
            output_dir=output_dir,
            now=now_local,
        )
        seen.add(target_identity(next_target))


def _pending_targets(
    *,
    targets: Iterable[RecordingTarget],
    seen: set[tuple[str, str, str]],
    now: datetime,
) -> list[RecordingTarget]:
    pending: list[RecordingTarget] = []
    for target in targets:
        key = target_identity(target)
        if key in seen:
            continue
        if now.astimezone(target.program.start_at.tzinfo) >= target.program.end_at:
            continue
        pending.append(target)
    return sorted(pending, key=lambda target: target.program.start_at)


def target_identity(target: RecordingTarget) -> tuple[str, str, str]:
    return (
        target.program.service,
        target.category,
        target.program.program_id or target.program.start_time,
    )


def _record_target(
    *,
    target: RecordingTarget,
    stream_urls: dict[str, str],
    output_dir: Path,
    now: datetime,
) -> None:
    start_at = target.program.start_at
    end_at = target.program.end_at
    stream_url = stream_urls.get(target.program.service)
    if not stream_url:
        raise ValueError(f"Missing stream URL for service {target.program.service}")

    duration_seconds = max(1, int((end_at - now).total_seconds()))
    output_path = target.output_path(output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_ffmpeg_bin()

    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        stream_url,
        "-vn",
        "-acodec",
        "copy",
        "-t",
        str(duration_seconds),
        str(output_path),
    ]
    print(f"Recording to {output_path} for {duration_seconds} seconds")
    subprocess.run(command, check=True)
    print(f"Finished recording: {output_path}")


def resolve_target_date(raw_value: str | None) -> date:
    if not raw_value:
        return datetime.now().date()
    return date.fromisoformat(raw_value)


def build_targets_for_day(
    *,
    area: str,
    services: Iterable[str],
    target_date: date,
    rules_path: str | Path | None = None,
) -> list[RecordingTarget]:
    programs = fetch_programs_for_day(area=area, services=services, target_date=target_date)
    rules = load_recording_rules(rules_path)
    return select_targets(programs, rules)
