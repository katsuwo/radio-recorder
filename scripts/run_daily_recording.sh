#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
AREA="${AREA:-130}"
SERVICES="${SERVICES:-r1,r3}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/recordings}"
TARGET_DATE="${TARGET_DATE:-}"
ENABLE_GDRIVE_SYNC="${ENABLE_GDRIVE_SYNC:-0}"
RECORDING_RULES_PATH="${RECORDING_RULES_PATH:-}"

cmd=(
  "${PYTHON_BIN}"
  "${PROJECT_ROOT}/scripts/record_daily_shows.py"
  --area "${AREA}"
  --services "${SERVICES}"
  --output-dir "${OUTPUT_DIR}"
  --record
)

if [[ -n "${TARGET_DATE}" ]]; then
  cmd+=(--date "${TARGET_DATE}")
fi

if [[ -n "${RECORDING_RULES_PATH}" ]]; then
  cmd+=(--rules "${RECORDING_RULES_PATH}")
fi

"${cmd[@]}"

if [[ "${ENABLE_GDRIVE_SYNC}" == "1" ]]; then
  "${PROJECT_ROOT}/scripts/sync_to_gdrive.sh"
fi
