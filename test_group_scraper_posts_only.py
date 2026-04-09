from __future__ import annotations

import unittest

import group_scraper_posts_only


class MergeContentBlocksTests(unittest.TestCase):
    def test_removes_blank_and_duplicate_blocks(self) -> None:
        merged = group_scraper_posts_only.merge_content_blocks(
            ["  Hello world  ", "", "Hello   world", "Second block"]
        )
        self.assertEqual(merged, "Hello world\nSecond block")


if __name__ == "__main__":
    unittest.main()
