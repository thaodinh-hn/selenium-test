from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "main-ai-bot-comment.py"
SPEC = importlib.util.spec_from_file_location("main_ai_bot_comment", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
main_ai_bot_comment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(main_ai_bot_comment)


class ResolveCommentTextTests(unittest.TestCase):
    def test_prefers_inline_comment(self) -> None:
        comment = main_ai_bot_comment.resolve_comment_text("  Xin chao\nban  ", None)
        self.assertEqual(comment, "Xin chao\nban")

    def test_reads_comment_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comment_path = Path(temp_dir) / "comment.txt"
            comment_path.write_text("Dong 1\r\n\r\nDong 2\r\n", encoding="utf-8")

            comment = main_ai_bot_comment.resolve_comment_text(None, str(comment_path))

        self.assertEqual(comment, "Dong 1\n\nDong 2")

    def test_rejects_empty_comment(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            main_ai_bot_comment.resolve_comment_text(" \n\t ", None)

        self.assertEqual(str(ctx.exception), "Comment content is empty.")


class BuildAiPromptTests(unittest.TestCase):
    def test_appends_instruction_suffix_once(self) -> None:
        prompt = main_ai_bot_comment.build_ai_prompt("Tra loi ngan gon")
        self.assertIn("Tra loi ngan gon", prompt)
        self.assertEqual(prompt.count(main_ai_bot_comment.AI_SUFFIX), 1)

    def test_rejects_empty_prompt(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            main_ai_bot_comment.build_ai_prompt("   ")

        self.assertEqual(
            str(ctx.exception),
            "OPENAI_PROMPT or --ai-prompt is required when --use-ai is enabled.",
        )


class _FakeEditor:
    def __init__(
        self,
        text_content: str = "",
        text: str = "",
        *,
        aria_label: str = "",
        aria_placeholder: str = "",
        displayed: bool = True,
    ) -> None:
        self._text_content = text_content
        self.text = text
        self._aria_label = aria_label
        self._aria_placeholder = aria_placeholder
        self._displayed = displayed

    def get_attribute(self, name: str) -> str:
        if name == "textContent":
            return self._text_content
        if name == "aria-label":
            return self._aria_label
        if name == "aria-placeholder":
            return self._aria_placeholder
        return ""

    def is_displayed(self) -> bool:
        return self._displayed


class EditorMatchTests(unittest.TestCase):
    def test_matches_comment_from_text_content(self) -> None:
        editor = _FakeEditor("Xin chao ban")
        self.assertTrue(main_ai_bot_comment.editor_contains_comment(editor, "Xin chao ban"))

    def test_falls_back_to_editor_text(self) -> None:
        editor = _FakeEditor("", "Dong 1\nDong 2")
        self.assertTrue(main_ai_bot_comment.editor_contains_comment(editor, "Dong 1\nDong 2"))

    def test_rejects_different_comment(self) -> None:
        editor = _FakeEditor("Noi dung khac")
        self.assertFalse(main_ai_bot_comment.editor_contains_comment(editor, "Xin chao"))

    def test_matches_when_facebook_text_content_drops_newline_spacing(self) -> None:
        editor = _FakeEditor(
            "Chúc bạn thi thật tốt nhéĐừng căng quá, cứ làm quen format là ok rồiThi xong nhớ lên update kết quả nha"
        )

        self.assertTrue(
            main_ai_bot_comment.editor_contains_comment(
                editor,
                "Chúc bạn thi thật tốt nhé\nĐừng căng quá, cứ làm quen format là ok rồi\nThi xong nhớ lên update kết quả nha",
            )
        )


class FindCommentEditorTests(unittest.TestCase):
    class _FakeDriver:
        def __init__(self, elements) -> None:
            self._elements = elements

        def find_elements(self, by: str, xpath: str):
            _ = by
            _ = xpath
            return list(self._elements)

    @patch.object(main_ai_bot_comment.time, "sleep", return_value=None)
    def test_falls_back_to_reply_editor_when_comment_editor_missing(self, _sleep) -> None:
        driver = self._FakeDriver(
            [
                _FakeEditor(
                    aria_label="Viết câu trả lời...",
                    aria_placeholder="Viết câu trả lời...",
                )
            ]
        )

        editor = main_ai_bot_comment.find_comment_editor(driver, timeout=0.1)

        self.assertIsNotNone(editor)

    @patch.object(main_ai_bot_comment.time, "sleep", return_value=None)
    def test_debug_scan_prints_candidate_details(self, _sleep) -> None:
        driver = self._FakeDriver(
            [
                _FakeEditor(
                    aria_label="Viết câu trả lời...",
                    aria_placeholder="Viết câu trả lời...",
                )
            ]
        )
        output = io.StringIO()

        with redirect_stdout(output):
            main_ai_bot_comment.find_comment_editor(
                driver,
                timeout=0.1,
                debug_scan=True,
            )

        self.assertIn("[find_comment_editor] scan #1 start", output.getvalue())
        self.assertIn("selected reply fallback candidate", output.getvalue())


class MainTests(unittest.TestCase):
    def test_main_exits_when_no_valid_cookies_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_path = Path(temp_dir) / "fb_cookie.txt"
            cookie_path.write_text("invalid-segment", encoding="utf-8")

            argv = [
                "main-ai-bot-comment.py",
                "--cookie-file",
                str(cookie_path),
                "--post-url",
                "https://www.facebook.com/groups/example/posts/123/",
                "--comment",
                "Xin chao",
            ]

            with patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    main_ai_bot_comment.main()

        self.assertEqual(str(ctx.exception), f"No valid cookies found in {cookie_path}")


if __name__ == "__main__":
    unittest.main()
