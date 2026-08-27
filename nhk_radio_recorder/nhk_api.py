from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://program-api.nhk.jp/v3/papiPgDateRadio"


class NhkApiError(RuntimeError):
    """Raised when the NHK API request cannot be completed."""


@dataclass(frozen=True)
class Program:
    service: str
    start_time: str
    end_time: str
    title: str
    subtitle: str | None = None
    program_id: str | None = None
    series_name: str | None = None
    genres: tuple[str, ...] = ()

    @property
    def start_at(self) -> datetime:
        return datetime.fromisoformat(self.start_time)

    @property
    def end_at(self) -> datetime:
        return datetime.fromisoformat(self.end_time)

    @property
    def display_name(self) -> str:
        return self.series_name or self.title


def build_schedule_url(*, service: str, area: str, target_date: str, api_key: str) -> str:
    query = urlencode(
        {
            "service": service.strip(),
            "area": area.strip(),
            "date": target_date.strip(),
            "key": api_key.strip(),
        }
    )
    return f"{API_URL}?{query}"


def default_api_key() -> str | None:
    return os.environ.get("NHK_API_KEY")


def fetch_schedule(
    *,
    service: str,
    area: str,
    target_date: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    key = (api_key or default_api_key() or "").strip()
    if not key:
        raise NhkApiError("NHK_API_KEY is not set.")

    resolved_date = (target_date or date.today().isoformat()).strip()
    resolved_service = service.strip()
    resolved_area = area.strip()
    url = build_schedule_url(
        service=resolved_service,
        area=resolved_area,
        target_date=resolved_date,
        api_key=key,
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "radio-recorder/0.1",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        context = (
            f"service={resolved_service} area={resolved_area} date={resolved_date} "
            f"url={build_schedule_url(service=resolved_service, area=resolved_area, target_date=resolved_date, api_key='[redacted]')}"
        )
        raise NhkApiError(f"NHK API returned HTTP {exc.code}: {detail} ({context})") from exc
    except URLError as exc:
        raise NhkApiError(f"NHK API request failed: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise NhkApiError("NHK API returned invalid JSON.") from exc


def extract_programs(payload: dict[str, Any]) -> list[Program]:
    programs = _find_program_dicts(payload)
    normalized: list[Program] = []
    for item in programs:
        normalized.append(
            Program(
                service=_pick_service(item, payload),
                start_time=_pick_start_time(item),
                end_time=_pick_end_time(item),
                title=_pick_title(item),
                subtitle=_optional_text(
                    item,
                    "subtitle",
                    "content",
                    "program_subtitle",
                    "description",
                    "programDescription",
                    "program_description",
                ),
                program_id=_optional_text(
                    item,
                    "id",
                    "program_id",
                    "event_id",
                    "programId",
                ),
                series_name=_pick_nested_text(
                    item,
                    ("about", "partOfSeries", "name"),
                    ("about", "identifierGroup", "radioSeriesName"),
                    ("identifierGroup", "radioSeriesName"),
                ),
                genres=_extract_genres(item),
            )
        )
    return normalized


def find_program_at(programs: list[Program], when: datetime) -> Program | None:
    for program in programs:
        if program.start_at <= when < program.end_at:
            return program
    return None


def _pick_service(item: dict[str, Any], payload: dict[str, Any]) -> str:
    service = _pick_nested_text(
        item,
        ("identifierGroup", "serviceId"),
        ("about", "identifierGroup", "serviceId"),
    )
    if service:
        return service

    for key in payload.keys():
        if key in {"r1", "r3"}:
            return key
    return ""


def _pick_start_time(item: dict[str, Any]) -> str:
    return _pick_text(
        item,
        "start_time",
        "start",
        "open_time",
        "startDate",
        "startDateTime",
        "start_date_time",
        "begin_time",
        "since",
    )


def _pick_end_time(item: dict[str, Any]) -> str:
    return _pick_text(
        item,
        "end_time",
        "end",
        "close_time",
        "endDate",
        "endDateTime",
        "end_date_time",
        "finish_time",
        "until",
    )


def _pick_title(item: dict[str, Any]) -> str:
    return _pick_text(
        item,
        "title",
        "program_title",
        "event_name",
        "name",
        "programName",
        "program_name",
    )


def _find_program_dicts(payload: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    _collect_program_dicts(payload, collected)
    return collected


def _collect_program_dicts(payload: Any, collected: list[dict[str, Any]]) -> None:
    if isinstance(payload, list):
        for item in payload:
            _collect_program_dicts(item, collected)
        return

    if not isinstance(payload, dict):
        return

    if _looks_like_program(payload):
        collected.append(payload)
        return

    for value in payload.values():
        if isinstance(value, (list, dict)):
            _collect_program_dicts(value, collected)


def _looks_like_program(item: dict[str, Any]) -> bool:
    return bool(_pick_start_time(item) and _pick_end_time(item) and _pick_title(item))


def _extract_genres(item: dict[str, Any]) -> tuple[str, ...]:
    raw_genres = _pick_nested_value(item, ("identifierGroup", "genre"))
    if not isinstance(raw_genres, list):
        return ()

    names: list[str] = []
    for genre in raw_genres:
        if not isinstance(genre, dict):
            continue
        for key in ("name1", "name2"):
            value = genre.get(key)
            if value:
                names.append(str(value))
    return tuple(names)


def _pick_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _optional_text(item: dict[str, Any], *keys: str) -> str | None:
    value = _pick_text(item, *keys)
    return value or None


def _pick_nested_text(item: dict[str, Any], *paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value = _pick_nested_value(item, path)
        if value:
            return str(value)
    return None


def _pick_nested_value(item: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = item
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
