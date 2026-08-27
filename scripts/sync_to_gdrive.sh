#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RCLONE_BIN="${RCLONE_BIN:-rclone}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/recordings}"
GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive}"
GDRIVE_REMOTE_PATH="${GDRIVE_REMOTE_PATH:-radio-recorder}"
RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-4}"
RCLONE_CHECKERS="${RCLONE_CHECKERS:-8}"

if ! command -v "${RCLONE_BIN}" >/dev/null 2>&1; then
  echo "error: ${RCLONE_BIN} was not found in PATH." >&2
  exit 1
fi

if [[ ! -d "${OUTPUT_DIR}" ]]; then
  echo "error: output directory does not exist: ${OUTPUT_DIR}" >&2
  exit 1
fi

"${RCLONE_BIN}" copy \
  "${OUTPUT_DIR}" \
  "${GDRIVE_REMOTE}:${GDRIVE_REMOTE_PATH}" \
  --create-empty-src-dirs \
  --transfers "${RCLONE_TRANSFERS}" \
  --checkers "${RCLONE_CHECKERS}"
