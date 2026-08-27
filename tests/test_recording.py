import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nhk_radio_recorder.nhk_api import Program
from nhk_radio_recorder.recording import (
    build_ffmpeg_command,
    fetch_programs_for_day,
    fetch_stream_urls_for_area,
    classify_program,
    format_target,
    load_recording_rules,
    parse_services,
    resolve_ffmpeg_bin,
    run_live_recording_schedule,
    sanitize_name,
    select_targets,
)


class RecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_recording_rules()

    def test_parse_services_defaults_to_r1_and_r3(self) -> None:
        self.assertEqual(parse_services(None), ("r1", "r3"))

    def test_parse_services_rejects_unknown_ids(self) -> None:
        with self.assertRaises(ValueError):
            parse_services("r1,r2")

    def test_classify_program_for_reading(self) -> None:
        program = Program(
            service="r1",
            start_time="2026-08-20T05:40:00+09:00",
            end_time="2026-08-20T05:55:00+09:00",
            title="まいにち朗読",
            subtitle="第104回",
        )

        target = classify_program(program, self.rules)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.category, "朗読")

    def test_classify_program_for_fm_drama(self) -> None:
        program = Program(
            service="r3",
            start_time="2026-08-20T22:00:00+09:00",
            end_time="2026-08-20T22:50:00+09:00",
            title="FMシアター",
            subtitle="ある物語",
        )

        target = classify_program(program, self.rules)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.category, "ラジオドラマ")
        self.assertEqual(target.folder_name, "radio_drama")

    def test_classify_program_excludes_minna_no_uta(self) -> None:
        program = Program(
            service="r3",
            start_time="2026-08-20T17:50:00+09:00",
            end_time="2026-08-20T17:55:00+09:00",
            title="みんなのうた「マスク・ド・カメロ」",
            genres=("audio drama",),
        )

        target = classify_program(program, self.rules)

        self.assertIsNone(target)

    def test_select_targets_deduplicates_per_service(self) -> None:
        program = Program(
            service="r1",
            start_time="2026-08-20T01:05:00+09:00",
            end_time="2026-08-20T02:00:03+09:00",
            title="ラジオ深夜便",
            subtitle="深夜便アーカイブス",
            program_id="abc",
        )

        targets = select_targets([program, program], self.rules)

        self.assertEqual(len(targets), 1)

    def test_output_path_includes_service_and_category(self) -> None:
        program = Program(
            service="r3",
            start_time="2026-08-20T22:00:00+09:00",
            end_time="2026-08-20T22:50:00+09:00",
            title="FMシアター",
            subtitle="ある物語",
            series_name="FMシアター",
        )

        target = classify_program(program, self.rules)

        self.assertIsNotNone(target)
        assert target is not None
        path = target.output_path(Path("recordings"))
        self.assertEqual(
            path,
            Path("recordings/r3/radio_drama/FMシアター/20260820_2200_FMシアター.m4a"),
        )

    def test_format_target_includes_service(self) -> None:
        program = Program(
            service="r1",
            start_time="2026-08-20T01:05:00+09:00",
            end_time="2026-08-20T02:00:03+09:00",
            title="ラジオ深夜便",
        )

        target = classify_program(program, self.rules)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(format_target(target), "[r1:ラジオ深夜便] 01:05-02:00 ラジオ深夜便")

    def test_sanitize_name_replaces_invalid_path_chars(self) -> None:
        self.assertEqual(sanitize_name('a/b:c*?"<>|'), "a_b_c_")

    @patch("nhk_radio_recorder.recording.shutil.which")
    def test_resolve_ffmpeg_bin_uses_configured_absolute_path(self, mock_which) -> None:
        with TemporaryDirectory() as temp_dir:
            ffmpeg_path = Path(temp_dir) / "ffmpeg"
            ffmpeg_path.write_text("", encoding="utf-8")
            with patch.dict("os.environ", {"FFMPEG_BIN": str(ffmpeg_path)}, clear=False):
                resolved = resolve_ffmpeg_bin()

        self.assertEqual(resolved, str(ffmpeg_path))
        mock_which.assert_not_called()

    @patch("nhk_radio_recorder.recording.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_resolve_ffmpeg_bin_uses_path_lookup(self, mock_which) -> None:
        with patch.dict("os.environ", {}, clear=False):
            resolved = resolve_ffmpeg_bin()

        self.assertEqual(resolved, "/usr/bin/ffmpeg")
        mock_which.assert_called()

    def test_load_recording_rules_accepts_custom_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.json"
            rules_path.write_text(
                """
{
  "exclude": [{"match": ["除外番組"]}],
  "include": [
    {
      "category": "カスタム",
      "folder_name": "custom",
      "match": ["特集"]
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )

            rules = load_recording_rules(rules_path)

        self.assertEqual(rules.include[0].category, "カスタム")
        self.assertEqual(rules.include[0].folder_name, "custom")
        self.assertEqual(rules.include[0].match, ("特集",))
        self.assertEqual(rules.exclude, (("除外番組",),))

    def test_build_ffmpeg_command_starts_from_live_edge(self) -> None:
        command = build_ffmpeg_command(
            ffmpeg_bin="/usr/bin/ffmpeg",
            stream_url="https://example.invalid/r1.m3u8",
            duration_seconds=600,
            output_path=Path("recordings/test.m4a"),
        )

        self.assertEqual(
            command,
            [
                "/usr/bin/ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-live_start_index",
                "-1",
                "-i",
                "https://example.invalid/r1.m3u8",
                "-vn",
                "-acodec",
                "copy",
                "-t",
                "600",
                "recordings/test.m4a",
            ],
        )

    def test_custom_rules_can_override_default_selection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.json"
            rules_path.write_text(
                """
{
  "include": [
    {
      "category": "トーク",
      "folder_name": "talk",
      "match": ["ことば"]
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            rules = load_recording_rules(rules_path)

        program = Program(
            service="r1",
            start_time="2026-08-20T05:40:00+09:00",
            end_time="2026-08-20T05:55:00+09:00",
            title="ことばの時間",
        )

        target = classify_program(program, rules)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.category, "トーク")
        self.assertEqual(target.folder_name, "talk")

    @patch("nhk_radio_recorder.recording.resolve_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("nhk_radio_recorder.recording.subprocess.run")
    def test_live_schedule_reloads_rules_and_skips_removed_future_target(
        self,
        mock_subprocess_run,
        _mock_ffmpeg,
    ) -> None:
        program = Program(
            service="r1",
            start_time="2026-08-21T11:50:00+09:00",
            end_time="2026-08-21T12:00:00+09:00",
            title="まいにち朗読",
        )
        target = classify_program(program, self.rules)
        self.assertIsNotNone(target)
        assert target is not None

        fetch_results = [[target], []]
        now_values = [
            Program(
                service="r1",
                start_time="2026-08-21T11:45:00+09:00",
                end_time="2026-08-21T11:45:01+09:00",
                title="dummy",
            ).start_at,
            Program(
                service="r1",
                start_time="2026-08-21T11:50:00+09:00",
                end_time="2026-08-21T11:50:01+09:00",
                title="dummy",
            ).start_at,
        ]
        sleeps: list[float] = []

        def fetch_targets_fn(**_: object) -> list:
            return fetch_results.pop(0)

        def now_fn() -> object:
            return now_values.pop(0)

        run_live_recording_schedule(
            area="130",
            services=("r1",),
            target_date=date(2026, 8, 21),
            stream_urls={"r1": "https://example.invalid/r1.m3u8"},
            output_dir=Path("recordings"),
            now_fn=now_fn,
            sleep_fn=sleeps.append,
            refresh_interval_seconds=300,
            fetch_targets_fn=fetch_targets_fn,
        )

        self.assertEqual(sleeps, [300.0])
        mock_subprocess_run.assert_not_called()

    @patch("nhk_radio_recorder.recording.resolve_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("nhk_radio_recorder.recording.subprocess.run")
    def test_live_schedule_reloads_rules_and_records_new_future_target(
        self,
        mock_subprocess_run,
        _mock_ffmpeg,
    ) -> None:
        late_program = Program(
            service="r1",
            start_time="2026-08-21T12:00:00+09:00",
            end_time="2026-08-21T12:05:00+09:00",
            title="まいにち朗読",
        )
        early_program = Program(
            service="r1",
            start_time="2026-08-21T11:50:00+09:00",
            end_time="2026-08-21T12:00:00+09:00",
            title="まいにち朗読",
        )
        late_target = classify_program(late_program, self.rules)
        early_target = classify_program(early_program, self.rules)
        self.assertIsNotNone(late_target)
        self.assertIsNotNone(early_target)
        assert late_target is not None
        assert early_target is not None

        fetch_results = [[late_target], [early_target, late_target], []]
        now_values = [
            Program(
                service="r1",
                start_time="2026-08-21T11:45:00+09:00",
                end_time="2026-08-21T11:45:01+09:00",
                title="dummy",
            ).start_at,
            Program(
                service="r1",
                start_time="2026-08-21T11:50:00+09:00",
                end_time="2026-08-21T11:50:01+09:00",
                title="dummy",
            ).start_at,
            Program(
                service="r1",
                start_time="2026-08-21T12:05:00+09:00",
                end_time="2026-08-21T12:05:01+09:00",
                title="dummy",
            ).start_at,
        ]
        sleeps: list[float] = []

        def fetch_targets_fn(**_: object) -> list:
            return fetch_results.pop(0)

        def now_fn() -> object:
            return now_values.pop(0)

        run_live_recording_schedule(
            area="130",
            services=("r1",),
            target_date=date(2026, 8, 21),
            stream_urls={"r1": "https://example.invalid/r1.m3u8"},
            output_dir=Path("recordings"),
            now_fn=now_fn,
            sleep_fn=sleeps.append,
            refresh_interval_seconds=300,
            fetch_targets_fn=fetch_targets_fn,
        )

        self.assertEqual(sleeps, [300.0])
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ffmpeg")
        self.assertTrue(command[-1].endswith("20260821_1150_まいにち朗読.m4a"))

    @patch("nhk_radio_recorder.recording.fetch_schedule")
    @patch("nhk_radio_recorder.recording.extract_programs")
    def test_fetch_programs_for_day_skips_previous_day_when_it_is_in_the_past(
        self,
        mock_extract_programs,
        mock_fetch_schedule,
    ) -> None:
        mock_fetch_schedule.return_value = {}
        mock_extract_programs.return_value = []

        with patch("nhk_radio_recorder.recording.datetime") as mock_datetime:
            mock_datetime.now.return_value.date.return_value = date(2026, 8, 20)
            fetch_programs_for_day(area="130", services=("r1",), target_date=date(2026, 8, 20))

        requested_dates = [call.kwargs["target_date"] for call in mock_fetch_schedule.call_args_list]
        self.assertEqual(requested_dates, ["2026-08-20"])

    @patch("nhk_radio_recorder.recording.urlopen")
    def test_fetch_stream_urls_for_area_reads_official_config_shape(self, mock_urlopen) -> None:
        xml_payload = b"""
<root>
  <stream_url>
    <data>
      <areakey>130</areakey>
      <r1hls>https://example.invalid/r1.m3u8</r1hls>
      <fmhls>https://example.invalid/r3.m3u8</fmhls>
    </data>
  </stream_url>
</root>
"""
        mock_urlopen.return_value.__enter__.return_value = BytesIO(xml_payload)

        urls = fetch_stream_urls_for_area("130")

        self.assertEqual(
            urls,
            {
                "r1": "https://example.invalid/r1.m3u8",
                "r3": "https://example.invalid/r3.m3u8",
            },
        )


if __name__ == "__main__":
    unittest.main()
