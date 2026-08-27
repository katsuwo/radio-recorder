#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nhk_radio_recorder.recording import fetch_stream_urls_for_area, parse_services, sanitize_name
from nhk_radio_recorder.nhk_api import NhkApiError, extract_programs, fetch_schedule, find_program_at


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record short NHK radio samples by downloading HLS segments.")
    parser.add_argument("--area", default="130", help="NHK area id. Default: 130")
    parser.add_argument("--services", default="r1,r3", help="Comma-separated services. Default: r1,r3")
    parser.add_argument("--seconds", type=int, default=60, help="Target duration in seconds. Default: 60")
    parser.add_argument(
        "--output-dir",
        default="recordings/smoke_test",
        help="Output directory. Default: recordings/smoke_test",
    )
    return parser.parse_args()


def read_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "radio-recorder/0.1"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def read_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "radio-recorder/0.1"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def resolve_media_playlist(master_url: str) -> str:
    content = read_text(master_url)
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return urljoin(master_url, line)
    raise ValueError(f"No media playlist found in {master_url}")


def decrypt_aes128_cbc(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    if plaintext:
        pad = plaintext[-1]
        if 0 < pad <= 16 and plaintext.endswith(bytes([pad]) * pad):
            plaintext = plaintext[:-pad]
    return plaintext


def download_sample(media_url: str, seconds: int) -> bytes:
    playlist_text = read_text(media_url)
    base_url = media_url
    key_uri = None
    media_sequence = 0
    current_duration = None
    total = 0.0
    chunks: list[bytes] = []

    lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            media_sequence = int(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-KEY:"):
            parts = {}
            for item in line.split(":", 1)[1].split(","):
                key, value = item.split("=", 1)
                parts[key] = value.strip('"')
            key_uri = urljoin(base_url, parts["URI"])

    if key_uri is None:
        raise ValueError("Playlist has no AES-128 key URI")

    key = read_bytes(key_uri)
    segment_index = 0
    for line in lines:
        if line.startswith("#EXTINF:"):
            current_duration = float(line.split(":", 1)[1].rstrip(","))
            continue
        if line.startswith("#"):
            continue
        if current_duration is None:
            continue
        segment_url = urljoin(base_url, line)
        ciphertext = read_bytes(segment_url)
        iv = (media_sequence + segment_index).to_bytes(16, "big")
        chunks.append(decrypt_aes128_cbc(ciphertext, key, iv))
        total += current_duration
        segment_index += 1
        current_duration = None
        if total >= seconds:
            break

    return b"".join(chunks)


def main() -> int:
    args = parse_args()
    services = parse_services(args.services)
    stream_urls = fetch_stream_urls_for_area(args.area)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now().astimezone()
    timestamp = captured_at.strftime("%Y%m%d_%H%M%S")

    for service in services:
        master_url = stream_urls[service]
        current_program = None
        title = "unknown_program"
        try:
            payload = fetch_schedule(service=service, area=args.area, target_date=captured_at.date().isoformat())
            programs = extract_programs(payload)
            current_program = find_program_at(programs, captured_at)
            title = current_program.title if current_program else title
        except NhkApiError:
            current_program = None
        media_url = resolve_media_playlist(master_url)
        audio = download_sample(media_url, args.seconds)
        output_stem = f"{timestamp}_{sanitize_name(service)}_{sanitize_name(title)}"
        output_path = output_dir / f"{output_stem}.aac"
        metadata_path = output_dir / f"{output_stem}.json"
        output_path.write_bytes(audio)
        metadata = {
            "captured_at": captured_at.isoformat(),
            "area": args.area,
            "service": service,
            "title": title,
            "subtitle": current_program.subtitle if current_program else None,
            "start_time": current_program.start_time if current_program else None,
            "end_time": current_program.end_time if current_program else None,
            "master_url": master_url,
            "media_url": media_url,
            "seconds": args.seconds,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
