from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fb_group_poster


class ResolveMessageTests(unittest.TestCase):
    def test_prefers_inline_message(self) -> None:
        message = fb_group_poster.resolve_message("  Hello\nWorld  ", None)
        self.assertEqual(message, "Hello\nWorld")

    def test_reads_message_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            message_path = Path(temp_dir) / "message.txt"
            message_path.write_text("Line 1\r\n\r\nLine 2\r\n", encoding="utf-8")

            message = fb_group_poster.resolve_message(None, str(message_path))

        self.assertEqual(message, "Line 1\n\nLine 2")

    def test_rejects_empty_message(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            fb_group_poster.resolve_message(" \n\t ", None)

        self.assertEqual(str(ctx.exception), "Post content is empty.")


class UnicodeHelperTests(unittest.TestCase):
    def test_detects_non_bmp_characters(self) -> None:
        self.assertTrue(fb_group_poster.contains_non_bmp_characters("Hello 🙏"))
        self.assertFalse(fb_group_poster.contains_non_bmp_characters("Hello"))

    def test_converts_text_to_bmp_safe_version(self) -> None:
        self.assertEqual(
            fb_group_poster.to_bmp_safe_text("Start 📝 middle 🙏 end"),
            "Start  middle  end",
        )


class _FakeEditor:
    def __init__(self, text_content: str = "", text: str = "") -> None:
        self._text_content = text_content
        self.text = text

    def get_attribute(self, name: str) -> str:
        if name == "textContent":
            return self._text_content
        return ""


class EditorMatchTests(unittest.TestCase):
    def test_matches_full_message_from_text_content(self) -> None:
        editor = _FakeEditor("Hello world")
        self.assertTrue(fb_group_poster.editor_contains_message(editor, "Hello world"))

    def test_rejects_partial_message(self) -> None:
        editor = _FakeEditor("Hello")
        self.assertFalse(fb_group_poster.editor_contains_message(editor, "Hello world"))

    def test_falls_back_to_editor_text(self) -> None:
        editor = _FakeEditor("", "Line 1\nLine 2")
        self.assertTrue(fb_group_poster.editor_contains_message(editor, "Line 1\nLine 2"))


if __name__ == "__main__":
    unittest.main()
