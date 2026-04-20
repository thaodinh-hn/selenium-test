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


class NormalizeCookieTests(unittest.TestCase):
    def test_adds_default_domain_and_path(self) -> None:
        normalized = main.normalize_cookie_for_facebook({"name": "c_user", "value": "123"})

        self.assertEqual(
            normalized,
            {
                "name": "c_user",
                "value": "123",
                "domain": ".facebook.com",
                "path": "/",
            },
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


class _FakeDriver:
    def __init__(self, *, c_user_value: str | None = "123") -> None:
        self.calls: list[tuple[str, object]] = []
        self._cookies: dict[str, dict[str, str]] = {}
        self._c_user_value = c_user_value

    def get(self, url: str) -> None:
        self.calls.append(("get", url))

    def add_cookie(self, cookie: dict[str, str]) -> None:
        self.calls.append(("add_cookie", dict(cookie)))
        self._cookies[cookie["name"]] = dict(cookie)

    def get_cookie(self, name: str):
        if name == "c_user" and self._c_user_value is None:
            return None
        if name == "c_user" and "c_user" in self._cookies:
            return {"name": "c_user", "value": self._c_user_value or ""}
        return self._cookies.get(name)


class LoginWithCookiesTests(unittest.TestCase):
    @patch("main.time.sleep", return_value=None)
    def test_adds_normalized_cookies_and_reloads(self, _sleep) -> None:
        driver = _FakeDriver()

        main.login_with_cookies(
            driver,
            [
                {"name": "c_user", "value": "123"},
                {"name": "xs", "value": "abc"},
            ],
        )

        self.assertEqual(
            driver.calls,
            [
                ("get", "https://www.facebook.com/"),
                (
                    "add_cookie",
                    {
                        "name": "c_user",
                        "value": "123",
                        "domain": ".facebook.com",
                        "path": "/",
                    },
                ),
                (
                    "add_cookie",
                    {
                        "name": "xs",
                        "value": "abc",
                        "domain": ".facebook.com",
                        "path": "/",
                    },
                ),
                ("get", "https://www.facebook.com/"),
            ],
        )

    @patch("main.time.sleep", return_value=None)
    def test_raises_when_session_not_active_after_reload(self, _sleep) -> None:
        driver = _FakeDriver(c_user_value=None)

        with self.assertRaises(RuntimeError) as ctx:
            main.login_with_cookies(
                driver,
                [
                    {"name": "c_user", "value": "123"},
                    {"name": "xs", "value": "abc"},
                ],
            )

        self.assertEqual(
            str(ctx.exception),
            "Facebook login via cookie did not become active. Refresh fb_cookie.txt with a valid logged-in cookie string.",
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
