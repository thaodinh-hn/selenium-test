from __future__ import annotations

import unittest
from unittest.mock import patch

import scrape_features.post_bodies.scraper as group_post_body_scraper


class CleanArticlePreviewTextTests(unittest.TestCase):
    def test_stops_before_comment_section_and_removes_metadata(self) -> None:
        article_text = """
        inspiringSeahorse5419
        8 tháng 4 lúc 19:01 ·
        Minh bị mất gốc và muốn học pte36
        1 7
        Xem thêm bình luận
        Katy Nguyen
        Em ib có cô kèm 1-1 online và offline nhé
        Viết bình luận công khai…
        """

        cleaned = group_post_body_scraper.clean_article_preview_text(
            article_text,
            "inspiringSeahorse5419",
        )

        self.assertEqual(cleaned, "Minh bị mất gốc và muốn học pte36")

    def test_keeps_multiline_post_body(self) -> None:
        article_text = """
        relaxingSquirrel5782
        4 tháng 4 lúc 12:03 ·
        Mình có thi Pte 4 năm trước, giờ mình chỉ cần điểm 24-36 thì có cần học trung tâm ko ạ?
        Mình dự định ôn trên apeuni và kiếm tutor học 1:1 vài ba buổi để ôn lại tips và phần writting.
        Thích
        Bình luận
        Chia sẻ
        """

        cleaned = group_post_body_scraper.clean_article_preview_text(
            article_text,
            "relaxingSquirrel5782",
        )

        self.assertEqual(
            cleaned,
            "Mình có thi Pte 4 năm trước, giờ mình chỉ cần điểm 24-36 thì có cần học trung tâm ko ạ?\n"
            "Mình dự định ôn trên apeuni và kiếm tutor học 1:1 vài ba buổi để ôn lại tips và phần writting.",
        )

    def test_stops_at_action_bar_before_comment_text(self) -> None:
        article_text = """
        Người tham gia ẩn danh
        8 tháng 4 lúc 17:41 ·
        Dạ chào các bạn, mình có tham khảo các trung tâm học PTE.
        Thích
        Bình luận
        Chia sẻ
        Hồ Thảo Nhiên
        Cố gắng luyện phát âm nhiều bằng Read Aloud em nhé.
        Viết câu trả lời...
        """

        cleaned = group_post_body_scraper.clean_article_preview_text(
            article_text,
            "Người tham gia ẩn danh",
        )

        self.assertEqual(
            cleaned,
            "Dạ chào các bạn, mình có tham khảo các trung tâm học PTE.",
        )


class ExtractPostUrlTests(unittest.TestCase):
    class _FakeLink:
        def __init__(self, href: str) -> None:
            self.href = href

        def get_attribute(self, name: str) -> str:
            if name == "href":
                return self.href
            return ""

    class _FakeContainer:
        def __init__(self, hrefs: list[str]) -> None:
            self.hrefs = hrefs

        def find_elements(self, *_args, **_kwargs):
            return [ExtractPostUrlTests._FakeLink(href) for href in self.hrefs]

    def test_falls_back_to_non_comment_post_url(self) -> None:
        container = self._FakeContainer(
            [
                "https://www.facebook.com/groups/1/posts/2/?comment_id=9",
                "https://www.facebook.com/groups/1/posts/2/?__tn__=%2CO%2CP-R",
            ]
        )

        with patch.object(
            group_post_body_scraper,
            "extract_post_url_from_context",
            return_value="https://www.facebook.com/groups/1/posts/2/?comment_id=9",
        ):
            url = group_post_body_scraper.extract_post_url(container)

        self.assertEqual(url, "https://www.facebook.com/groups/1/posts/2/")

    def test_keeps_primary_post_url_when_already_clean(self) -> None:
        container = self._FakeContainer([])

        with patch.object(
            group_post_body_scraper,
            "extract_post_url_from_context",
            return_value="https://www.facebook.com/groups/1/posts/2/",
        ):
            url = group_post_body_scraper.extract_post_url(container)

        self.assertEqual(url, "https://www.facebook.com/groups/1/posts/2/")


if __name__ == "__main__":
    unittest.main()
