#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

mkdir -p "${SYSTEMD_USER_DIR}"

cp "${PROJECT_ROOT}/systemd/radio-recorder.service" "${SYSTEMD_USER_DIR}/"
cp "${PROJECT_ROOT}/systemd/radio-recorder.timer" "${SYSTEMD_USER_DIR}/"

systemctl --user daemon-reload
systemctl --user enable --now radio-recorder.timer

echo "Installed user units into ${SYSTEMD_USER_DIR}"
echo "Next commands:"
echo "  systemctl --user start radio-recorder.service"
echo "  journalctl --user -u radio-recorder.service -n 100 --no-pager"
