from datetime import datetime
import unittest

from nhk_radio_recorder.nhk_api import Program, build_schedule_url, extract_programs, find_program_at


class NhkApiTests(unittest.TestCase):
    def test_build_schedule_url(self) -> None:
        url = build_schedule_url(
            service="r1",
            area="130",
            target_date="2026-08-20",
            api_key="secret",
        )
        self.assertIn("service=r1", url)
        self.assertIn("area=130", url)
        self.assertIn("date=2026-08-20", url)
        self.assertIn("key=secret", url)

    def test_build_schedule_url_strips_whitespace(self) -> None:
        url = build_schedule_url(
            service=" r1 ",
            area=" 130 ",
            target_date=" 2026-08-20 ",
            api_key=" secret ",
        )
        self.assertIn("service=r1", url)
        self.assertIn("area=130", url)
        self.assertIn("date=2026-08-20", url)
        self.assertIn("key=secret", url)

    def test_extract_programs_from_nested_service_payload(self) -> None:
        payload = {
            "list": {
                "r1": [
                    {
                        "start_time": "2026-08-20T06:00:00+09:00",
                        "end_time": "2026-08-20T06:55:00+09:00",
                        "title": "NHKニュース",
                        "subtitle": "朝のニュース",
                        "id": "abc123",
                    }
                ]
            }
        }

        programs = extract_programs(payload)

        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0].service, "")
        self.assertEqual(programs[0].title, "NHKニュース")
        self.assertEqual(programs[0].subtitle, "朝のニュース")
        self.assertEqual(programs[0].program_id, "abc123")

    def test_extract_programs_skips_non_program_wrappers(self) -> None:
        payload = {
            "result": {
                "meta": {"count": 1},
                "services": [
                    {
                        "service": {"id": "r1", "name": "NHK AM"},
                        "programs": [
                            {
                                "program": {
                                    "start_time": "2026-08-20T07:00:00+09:00",
                                    "end_time": "2026-08-20T07:15:00+09:00",
                                    "title": "ニュース",
                                }
                            }
                        ],
                    }
                ],
            }
        }

        programs = extract_programs(payload)

        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0].service, "")
        self.assertEqual(programs[0].title, "ニュース")
        self.assertEqual(programs[0].start_time, "2026-08-20T07:00:00+09:00")

    def test_extract_programs_from_actual_nhk_shape(self) -> None:
        payload = {
            "r1": {
                "publishedOn": [
                    {
                        "type": "BroadcastService",
                        "id": "bs-r1-130",
                        "name": "NHK AM放送",
                    }
                ],
                "publication": [
                    {
                        "type": "BroadcastEvent",
                        "id": "r1-130-2026082068357",
                        "name": "マイあさ！５時台",
                        "description": "説明",
                        "startDate": "2026-08-20T05:00:03+09:00",
                        "endDate": "2026-08-20T05:40:00+09:00",
                        "misc": {
                            "programType": "program",
                        },
                    }
                ],
            }
        }

        programs = extract_programs(payload)

        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0].service, "r1")
        self.assertEqual(programs[0].title, "マイあさ！５時台")
        self.assertEqual(programs[0].subtitle, "説明")
        self.assertEqual(programs[0].start_time, "2026-08-20T05:00:03+09:00")
        self.assertEqual(programs[0].end_time, "2026-08-20T05:40:00+09:00")

    def test_find_program_at_returns_matching_program(self) -> None:
        programs = [
            Program(
                service="r1",
                start_time="2026-08-21T09:05:00+09:00",
                end_time="2026-08-21T09:55:00+09:00",
                title="番組A",
            ),
            Program(
                service="r1",
                start_time="2026-08-21T10:05:00+09:00",
                end_time="2026-08-21T10:55:00+09:00",
                title="番組B",
            ),
        ]

        program = find_program_at(programs, datetime.fromisoformat("2026-08-21T09:19:00+09:00"))

        self.assertIsNotNone(program)
        assert program is not None
        self.assertEqual(program.title, "番組A")


if __name__ == "__main__":
    unittest.main()
