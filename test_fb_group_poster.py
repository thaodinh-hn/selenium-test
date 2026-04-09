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


if __name__ == "__main__":
    unittest.main()
