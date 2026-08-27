#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/recordings}"
GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive}"
GDRIVE_REMOTE_PATH="${GDRIVE_REMOTE_PATH:-radio-recorder}"
RCLONE_BIN="${RCLONE_BIN:-rclone}"
TEST_SERVICE="${TEST_SERVICE:-r3}"
TEST_CATEGORY="${TEST_CATEGORY:-radio_drama}"
TEST_SERIES="${TEST_SERIES:-Sync Test Series}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d_%H%M%S)}"
TEST_TITLE="${TEST_TITLE:-sync_test_${TIMESTAMP}}"

if ! command -v "${RCLONE_BIN}" >/dev/null 2>&1; then
  echo "error: ${RCLONE_BIN} was not found in PATH." >&2
  exit 1
fi

relative_path="${TEST_SERVICE}/${TEST_CATEGORY}/${TEST_SERIES}/${TIMESTAMP}_${TEST_TITLE}.m4a"
local_path="${OUTPUT_DIR}/${relative_path}"
remote_path="${GDRIVE_REMOTE}:${GDRIVE_REMOTE_PATH}/${relative_path}"

mkdir -p "$(dirname "${local_path}")"
printf 'radio-recorder sync test %s\n' "${TIMESTAMP}" > "${local_path}"

echo "Created test file: ${local_path}"
"${PROJECT_ROOT}/scripts/sync_to_gdrive.sh"

"${RCLONE_BIN}" lsf "${remote_path}" >/dev/null
echo "Verified remote file: ${remote_path}"
