import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GDriveScriptTests(unittest.TestCase):
    def test_verify_gdrive_sync_preserves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "recordings"
            remote_root = temp_path / "remote"
            fake_rclone = temp_path / "fake_rclone.sh"
            fake_rclone.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "cmd=\"$1\"\n"
                "shift\n"
                "remote_root=\"${FAKE_RCLONE_REMOTE_ROOT:?}\"\n"
                "resolve_remote() {\n"
                "  local remote_spec=\"$1\"\n"
                "  local remote_name=\"${remote_spec%%:*}\"\n"
                "  local remote_path=\"${remote_spec#*:}\"\n"
                "  if [[ \"${remote_name}\" == \"${remote_spec}\" ]]; then\n"
                "    echo \"invalid remote: ${remote_spec}\" >&2\n"
                "    exit 1\n"
                "  fi\n"
                "  printf '%s/%s/%s\\n' \"${remote_root}\" \"${remote_name}\" \"${remote_path}\"\n"
                "}\n"
                "if [[ \"${cmd}\" == \"copy\" ]]; then\n"
                "  src=\"$1\"\n"
                "  dest=\"$2\"\n"
                "  dest_path=\"$(resolve_remote \"${dest}\")\"\n"
                "  mkdir -p \"${dest_path}\"\n"
                "  cp -R \"${src}/.\" \"${dest_path}/\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${cmd}\" == \"lsf\" ]]; then\n"
                "  target_path=\"$(resolve_remote \"$1\")\"\n"
                "  if [[ -e \"${target_path}\" ]]; then\n"
                "    basename \"${target_path}\"\n"
                "    exit 0\n"
                "  fi\n"
                "  exit 1\n"
                "fi\n"
                "echo \"unsupported command: ${cmd}\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_rclone.chmod(fake_rclone.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "OUTPUT_DIR": str(output_dir),
                    "GDRIVE_REMOTE": "gdrive",
                    "GDRIVE_REMOTE_PATH": "radio-recorder",
                    "RCLONE_BIN": str(fake_rclone),
                    "FAKE_RCLONE_REMOTE_ROOT": str(remote_root),
                    "TEST_SERVICE": "r3",
                    "TEST_CATEGORY": "radio_drama",
                    "TEST_SERIES": "Sync Test Series",
                    "TIMESTAMP": "20260820_130000",
                    "TEST_TITLE": "sync_test_fixture",
                }
            )

            subprocess.run(
                ["bash", str(PROJECT_ROOT / "scripts" / "verify_gdrive_sync.sh")],
                check=True,
                cwd=str(PROJECT_ROOT),
                env=env,
            )

            local_file = (
                output_dir
                / "r3"
                / "radio_drama"
                / "Sync Test Series"
                / "20260820_130000_sync_test_fixture.m4a"
            )
            remote_file = (
                remote_root
                / "gdrive"
                / "radio-recorder"
                / "r3"
                / "radio_drama"
                / "Sync Test Series"
                / "20260820_130000_sync_test_fixture.m4a"
            )

            self.assertTrue(local_file.exists())
            self.assertTrue(remote_file.exists())
            self.assertEqual(local_file.read_text(encoding="utf-8"), remote_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
