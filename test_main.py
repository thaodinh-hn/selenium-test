from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class ConvertRawCookieTests(unittest.TestCase):
    def test_parses_cookie_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_path = Path(temp_dir) / "fb_cookie.txt"
            cookie_path.write_text("c_user=123; xs=abc=def ; datr = value", encoding="utf-8")

            cookies = main.convert_raw_cookie(cookie_path)

        self.assertEqual(
            cookies,
            [
                {"name": "c_user", "value": "123"},
                {"name": "xs", "value": "abc=def"},
                {"name": "datr", "value": "value"},
            ],
        )

    def test_skips_invalid_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_path = Path(temp_dir) / "fb_cookie.txt"
            cookie_path.write_text("foo=bar; invalid; =missing_name; ; baz=qux", encoding="utf-8")

            cookies = main.convert_raw_cookie(cookie_path)

        self.assertEqual(
            cookies,
            [
                {"name": "foo", "value": "bar"},
                {"name": "baz", "value": "qux"},
            ],
        )


class BuildProfileUrlTests(unittest.TestCase):
    def test_uses_profile_php_for_numeric_uid(self) -> None:
        self.assertEqual(
            main.build_profile_url("100092652609466"),
            "https://www.facebook.com/profile.php?id=100092652609466",
        )

    def test_uses_slug_path_for_username(self) -> None:
        self.assertEqual(
            main.build_profile_url("some.profile.slug"),
            "https://www.facebook.com/some.profile.slug",
        )


class MainTests(unittest.TestCase):
    def test_main_exits_when_no_valid_cookies_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_path = Path(temp_dir) / "fb_cookie.txt"
            cookie_path.write_text("invalid-segment", encoding="utf-8")

            argv = [
                "main.py",
                "--cookie-file",
                str(cookie_path),
                "--uid",
                "123456789",
            ]

            with patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    main.main()

        self.assertEqual(str(ctx.exception), f"No valid cookies found in {cookie_path}")


if __name__ == "__main__":
    unittest.main()
