from __future__ import annotations

import unittest
from unittest.mock import patch

import scrape_features.posts_only.scraper as group_scraper_posts_only


class MergeContentBlocksTests(unittest.TestCase):
    def test_removes_blank_and_duplicate_blocks(self) -> None:
        merged = group_scraper_posts_only.merge_content_blocks(
            ["  Hello world  ", "", "Hello   world", "Second block"]
        )
        self.assertEqual(merged, "Hello world\nSecond block")


class ScrapeMultipleGroupsOnlyTests(unittest.TestCase):
    def test_writes_interim_results_and_continues_after_group_failure(self) -> None:
        posts_group_1 = [
            {
                "post_key": "post-1",
                "author": "A",
                "content": "First",
                "post_url": "https://example.com/1",
                "group_url": "https://example.com/group-1",
                "scraped_at_utc": "2026-04-11T00:00:00+00:00",
            }
        ]
        posts_group_3 = [
            {
                "post_key": "post-2",
                "author": "B",
                "content": "Second",
                "post_url": "https://example.com/2",
                "group_url": "https://example.com/group-3",
                "scraped_at_utc": "2026-04-11T00:01:00+00:00",
            }
        ]

        with patch.object(
            group_scraper_posts_only,
            "scrape_group_posts_only",
            side_effect=[posts_group_1, RuntimeError("boom"), posts_group_3],
        ), patch.object(group_scraper_posts_only, "write_posts_to_csv") as write_mock:
            posts = group_scraper_posts_only.scrape_multiple_groups_only(
                [
                    "https://example.com/group-1",
                    "https://example.com/group-2",
                    "https://example.com/group-3",
                ],
                [{"name": "c_user", "value": "123"}],
                output_path="out.csv",
                max_posts=10,
                max_scrolls=5,
                min_delay=1.0,
                max_delay=2.0,
            )

        self.assertEqual(posts, posts_group_1 + posts_group_3)
        self.assertEqual(write_mock.call_count, 2)
        self.assertEqual(write_mock.call_args_list[0].args[0], posts_group_1)
        self.assertEqual(write_mock.call_args_list[1].args[0], posts_group_1 + posts_group_3)


if __name__ == "__main__":
    unittest.main()
