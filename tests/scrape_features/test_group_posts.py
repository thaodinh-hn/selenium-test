from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import scrape_features.group_posts.scraper as group_scraper


class CleanTextTests(unittest.TestCase):
    def test_collapses_whitespace(self) -> None:
        self.assertEqual(group_scraper.clean_text("  a \n b\t c  "), "a b c")


class BuildPostKeyTests(unittest.TestCase):
    def test_prefers_post_url_when_available(self) -> None:
        first = group_scraper.build_post_key("https://facebook.com/posts/1", "A", "B")
        second = group_scraper.build_post_key("https://facebook.com/posts/1", "X", "Y")
        self.assertEqual(first, second)

    def test_falls_back_to_author_and_content(self) -> None:
        first = group_scraper.build_post_key("", "Author", "Hello world")
        second = group_scraper.build_post_key("", " Author ", "Hello   world")
        self.assertEqual(first, second)


class NormalizeGroupUrlsTests(unittest.TestCase):
    def test_uses_default_when_empty(self) -> None:
        self.assertEqual(
            group_scraper.normalize_group_urls(None),
            [group_scraper.DEFAULT_GROUP_URL.rstrip("/")],
        )

    def test_deduplicates_and_trims_urls(self) -> None:
        urls = [
            " https://www.facebook.com/groups/1443095370326256/ ",
            "https://www.facebook.com/groups/913609150407483",
            "https://www.facebook.com/groups/1443095370326256",
        ]
        self.assertEqual(
            group_scraper.normalize_group_urls(urls),
            [
                "https://www.facebook.com/groups/1443095370326256",
                "https://www.facebook.com/groups/913609150407483",
            ],
        )


class WritePostsToCsvTests(unittest.TestCase):
    def test_writes_expected_columns(self) -> None:
        rows = [
            {
                "post_key": "abc",
                "author": "Mario",
                "content": "Sample post",
                "post_url": "https://facebook.com/posts/1",
                "group_url": "https://facebook.com/groups/1",
                "scraped_at_utc": "2026-04-06T16:00:00+00:00",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "posts.csv"
            group_scraper.write_posts_to_csv(rows, output_path)

            with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                written_rows = list(reader)

        self.assertEqual(written_rows, rows)


if __name__ == "__main__":
    unittest.main()
