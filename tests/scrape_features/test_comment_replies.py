from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scrape_features.comment_replies import execute_plan
from scrape_features.comment_replies.generate_plan import build_comment_idea, generate_plan


class BuildCommentIdeaTests(unittest.TestCase):
    def test_handles_beginner_signal(self) -> None:
        comment = build_comment_idea("Mình mất gốc tiếng Anh và mới bắt đầu học PTE")
        self.assertIn("mới bắt đầu", comment)

    def test_handles_target_signal(self) -> None:
        comment = build_comment_idea("Target của mình là 58, cần cải thiện điểm nghe")
        self.assertIn("mục tiêu", comment)


class GeneratePlanTests(unittest.TestCase):
    def test_generates_plan_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "post_bodies.csv"
            output_path = Path(temp_dir) / "comment_plan.csv"
            with input_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "post_key",
                        "author",
                        "content",
                        "post_url",
                        "group_url",
                        "scraped_at_utc",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "post_key": "pk-1",
                        "author": "A",
                        "content": "Mình cần tips để thi tốt hơn.",
                        "post_url": "https://example.com/post/1",
                        "group_url": "https://example.com/group/1",
                        "scraped_at_utc": "2026-04-18T12:00:00+00:00",
                    }
                )

            count = generate_plan(input_path, output_path, overwrite=True)
            self.assertEqual(count, 1)

            with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["post_key"], "pk-1")
        self.assertEqual(rows[0]["status"], "pending")
        self.assertTrue(rows[0]["generated_comment"])


class ExecutePlanHelperTests(unittest.TestCase):
    class _FakeDriver:
        def __init__(self, current_url: str, *, has_login_inputs: bool = False) -> None:
            self.current_url = current_url
            self.has_login_inputs = has_login_inputs

        def find_elements(self, by: str, xpath: str):
            _ = by
            if xpath == "//input[@name='email' or @name='pass']" and self.has_login_inputs:
                return [object()]
            return []

    class _FakeEditor:
        def __init__(self, text: str) -> None:
            self.text = text

        def get_attribute(self, name: str) -> str:
            if name == "textContent":
                return self.text
            return ""

    def test_ensure_post_context_detects_redirect(self) -> None:
        driver = self._FakeDriver("https://www.facebook.com/")
        with self.assertRaises(execute_plan.CommentExecutionError) as ctx:
            execute_plan.ensure_post_context(
                driver,
                "https://www.facebook.com/groups/ptetalents/posts/2021853212067473/",
            )

        self.assertEqual(ctx.exception.status_code, "redirected_or_unavailable_post")

    def test_ensure_post_context_detects_login_page(self) -> None:
        driver = self._FakeDriver("https://www.facebook.com/login/", has_login_inputs=True)
        with self.assertRaises(execute_plan.CommentExecutionError) as ctx:
            execute_plan.ensure_post_context(
                driver,
                "https://www.facebook.com/groups/ptetalents/posts/2021853212067473/",
            )

        self.assertEqual(ctx.exception.status_code, "redirected_or_unavailable_post")

    def test_editor_contains_comment_matches_clean_text(self) -> None:
        editor = self._FakeEditor("Chuc ban thi that tot nhe")
        self.assertTrue(
            execute_plan.editor_contains_comment(editor, "Chuc ban thi that tot nhe")
        )
        self.assertFalse(
            execute_plan.editor_contains_comment(editor, "Noi dung khac")
        )


if __name__ == "__main__":
    unittest.main()
