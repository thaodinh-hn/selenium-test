from __future__ import annotations

import argparse
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from scrape_features.group_posts.scraper import (
    DEFAULT_GROUP_URL,
    build_post_key,
    clean_text,
    close_popups,
    dump_debug,
    expand_see_more,
    extract_post_url as extract_post_url_from_context,
    login_with_cookies,
    normalize_group_urls,
    random_pause,
    write_posts_to_csv,
)
from main import build_driver, convert_raw_cookie


POST_MESSAGE_XPATH = (
    "//div[@data-ad-rendering-role='story_message']"
    "|//*[@data-ad-comet-preview='message'"
    " and not(ancestor::*[@data-ad-rendering-role='story_message'])]"
    "|//*[@data-ad-preview='message'"
    " and not(ancestor::*[@data-ad-rendering-role='story_message'])"
    " and not(ancestor::*[@data-ad-comet-preview='message'])]"
)

MESSAGE_NODE_XPATH = (
    ".//*[@data-ad-preview='message'"
    " or @data-ad-comet-preview='message'"
    " or @data-ad-rendering-role='story_message']"
)

POST_CONTEXT_XPATH = (
    "./ancestor::div[.//a[contains(@href,'/posts/')"
    " or contains(@href,'story_fbid=')"
    " or contains(@href,'/permalink/')]][1]"
)

COMMENT_BOUNDARY_XPATH = (
    ".//*[contains(normalize-space(), 'Xem thêm bình luận')"
    " or contains(normalize-space(), 'View more comments')"
    " or @data-ad-rendering-role='comment_button'"
    " or contains(@aria-label, 'Viết bình luận')"
    " or contains(@aria-label, 'Write comment')"
    " or contains(@aria-label, 'Comment')"
    " or contains(@aria-placeholder, 'Viết bình luận công khai')"
    " or contains(@aria-placeholder, 'Write a public comment')"
    " or contains(@aria-placeholder, 'Viết câu trả lời')"
    " or contains(@aria-placeholder, 'Write a reply')"
    " or contains(@aria-label, 'Viết bình luận công khai')"
    " or contains(@aria-label, 'Write a public comment')"
    " or (@role='article' and contains(@aria-label, 'Bình luận dưới tên'))"
    " or (@role='article' and contains(@aria-label, 'Comment by'))]"
)


METADATA_LINE_PATTERNS = [
    re.compile(r"^\d+\s*$"),
    re.compile(r"^\d+[\s·]+\d+.*$"),
    re.compile(r"^\d+\s*(phút|giờ|ngày|tuần|tháng|năm).*$", re.IGNORECASE),
    re.compile(r"^(hôm qua|yesterday|just now).*$", re.IGNORECASE),
    re.compile(r"^.*\slúc\s\d{1,2}:\d{2}.*$", re.IGNORECASE),
]

IGNORED_EXACT_LINES = {
    "Facebook",
    "Thích",
    "Bình luận",
    "Chia sẻ",
    "Like",
    "Comment",
    "Share",
    "Quản trị viên",
    "Admin",
    "Người tham gia ẩn danh",
    "Anonymous participant",
    "Theo dõi",
    "Follow",
    "Xem thêm bình luận",
    "View more comments",
    "Viết bình luận",
    "Viết bình luận công khai…",
    "Viết câu trả lời...",
    "Write a public comment…",
    "Write a reply...",
}

ACTION_BAR_BOUNDARY_LINES = {
    "Thích",
    "Bình luận",
    "Chia sẻ",
    "Like",
    "Comment",
    "Share",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scroll Facebook groups and export only the original post body, excluding comments."
    )
    parser.add_argument(
        "--cookie-file",
        default="fb_cookie.txt",
        help="Path to a raw Facebook cookie string file.",
    )
    parser.add_argument(
        "--group-url",
        action="append",
        dest="group_urls",
        help="Facebook group URL to scrape. Repeat this flag to scrape multiple groups.",
    )
    parser.add_argument(
        "--output",
        default="scrape_features/post_bodies/data/group_post_bodies.csv",
        help="CSV file to write scraped post bodies to.",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=30,
        help="Stop after collecting this many unique post bodies per group.",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=20,
        help="Stop after this many scroll cycles if enough posts are not found.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=1.5,
        help="Minimum seconds to wait between scroll actions.",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=4.0,
        help="Maximum seconds to wait between scroll actions.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode.",
    )
    return parser.parse_args()


def find_post_message_nodes(driver):
    from selenium.webdriver.common.by import By

    return driver.find_elements(By.XPATH, POST_MESSAGE_XPATH)


def expand_post_see_more(driver) -> None:
    from selenium.webdriver.common.by import By

    more_xpath = (
        "//*[self::div or self::span][normalize-space()='See more' or normalize-space()='Xem thêm']"
        "/ancestor::*[@role='button'][1]"
        "|//*[@role='button'][.//span[normalize-space()='See more' or normalize-space()='Xem thêm']]"
    )
    for button in driver.find_elements(By.XPATH, more_xpath):
        try:
            if button.is_displayed():
                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.2)
        except Exception:  # pragma: no cover
            continue


def find_post_container(driver, message_node):
    script = """
    const start = arguments[0];
    const hasPostLink = (el) => Boolean(
      el.querySelector('a[href*="/posts/"]:not([href*="comment_id="]), ' +
                       'a[href*="story_fbid="]:not([href*="comment_id="]), ' +
                       'a[href*="/permalink/"]:not([href*="comment_id="])')
    );
    const hasActionBar = (el) => Boolean(
      el.querySelector('[data-ad-rendering-role="comment_button"], ' +
                       '[data-ad-rendering-role="share_button"], ' +
                       '[data-ad-rendering-role="like_button"]')
    );

    let el = start;
    while (el && el.nodeType === 1) {
      if (hasPostLink(el) && hasActionBar(el)) {
        return el;
      }
      el = el.parentElement;
    }

    el = start;
    while (el && el.nodeType === 1) {
      if (hasPostLink(el)) {
        return el;
      }
      el = el.parentElement;
    }

    return start;
    """
    return driver.execute_script(script, message_node)


def find_post_context_from_message(driver, message_node):
    try:
        context = message_node.find_element("xpath", POST_CONTEXT_XPATH)
        if context:
            return context
    except Exception:
        pass
    return find_post_container(driver, message_node)


def extract_message_text(message_node) -> str:
    text = clean_text(message_node.text)
    if text:
        return text

    try:
        return clean_text(message_node.get_attribute("innerText") or "")
    except Exception:  # pragma: no cover
        return ""


def extract_post_url(container) -> str:
    url = extract_post_url_from_context(container)
    if url and "comment_id=" not in url:
        return url

    xpath = (
        ".//a[contains(@href,'/posts/')"
        " or contains(@href,'/permalink/')"
        " or contains(@href,'story_fbid=')]"
    )
    for link in container.find_elements("xpath", xpath):
        href = (link.get_attribute("href") or "").strip()
        if not href or "comment_id=" in href:
            continue
        return href.split("?")[0]

    return ""


def extract_author(container) -> str:
    from selenium.webdriver.common.by import By

    author_xpath = (
        ".//*[@data-ad-rendering-role='profile_name']//span"
        "|.//h2//span"
        "|.//h3//span"
        "|.//strong//span"
        "|.//a[@role='link']//strong//span"
    )
    for node in container.find_elements(By.XPATH, author_xpath):
        text = clean_text(node.text)
        if not text or text in IGNORED_EXACT_LINES:
            continue
        return text
    return ""


def merge_content_blocks(blocks: list[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()

    for block in blocks:
        text = clean_text(block)
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)

    return "\n".join(merged)


def find_comment_boundary_y(article) -> int | None:
    from selenium.webdriver.common.by import By

    positions: list[int] = []
    for element in article.find_elements(By.XPATH, COMMENT_BOUNDARY_XPATH):
        try:
            positions.append(int(element.location["y"]))
        except Exception:  # pragma: no cover
            continue

    return min(positions) if positions else None


def extract_primary_message_cluster(article, boundary_y: int | None) -> str:
    from selenium.webdriver.common.by import By

    candidates: list[tuple[int, str]] = []
    for node in article.find_elements(By.XPATH, MESSAGE_NODE_XPATH):
        try:
            text = clean_text(node.text)
            if not text:
                continue
            y = int(node.location["y"])
        except Exception:  # pragma: no cover
            continue

        if boundary_y is not None and y >= boundary_y - 5:
            continue
        candidates.append((y, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0])
    first_y = candidates[0][0]
    merged: list[str] = []
    previous_y = first_y

    for y, text in candidates:
        if boundary_y is None and y - first_y > 220:
            break
        if merged and y - previous_y > 140:
            break
        merged.append(text)
        previous_y = y

    return merge_content_blocks(merged)


def is_metadata_line(line: str, author: str) -> bool:
    normalized = clean_text(line)
    if not normalized:
        return True
    if normalized == clean_text(author):
        return True
    if normalized in IGNORED_EXACT_LINES:
        return True
    if normalized.startswith("Xem thêm"):
        return True
    if normalized.startswith("See more"):
        return True

    lower = normalized.lower()
    if "viết bình luận công khai" in lower or "write a public comment" in lower:
        return True
    if lower in {"tác giả", "author"}:
        return True

    for pattern in METADATA_LINE_PATTERNS:
        if pattern.match(normalized):
            return True

    return False


def clean_article_preview_text(article_text: str, author: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    for raw_line in article_text.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        if line in seen:
            continue
        seen.add(line)
        if "xem thêm bình luận" in line.lower() or "view more comments" in line.lower():
            break
        if "viết bình luận công khai" in line.lower() or "write a public comment" in line.lower():
            break
        if "viết câu trả lời" in line.lower() or "write a reply" in line.lower():
            break
        if line in ACTION_BAR_BOUNDARY_LINES:
            break
        if is_metadata_line(line, author):
            continue
        lines.append(line)

    return "\n".join(lines[:8])


def extract_fallback_body_text(article, author: str) -> str:
    try:
        article_text = article.get_attribute("innerText") or ""
    except Exception:  # pragma: no cover
        return ""
    return clean_article_preview_text(article_text, author)


def extract_post_body(article, author: str) -> str:
    boundary_y = find_comment_boundary_y(article)

    primary = extract_primary_message_cluster(article, boundary_y)
    if primary:
        return primary

    return extract_fallback_body_text(article, author)


def extract_post_record_from_message_node(driver, message_node, group_url: str) -> dict[str, str] | None:
    container = find_post_context_from_message(driver, message_node)
    author = extract_author(container)
    post_url = extract_post_url(container)
    content = extract_message_text(message_node)
    if not content:
        content = extract_post_body(container, author)

    if not content:
        return None

    return {
        "post_key": build_post_key(post_url, author, content),
        "author": author,
        "content": content,
        "post_url": post_url,
        "group_url": group_url,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def scrape_group_post_bodies(
    group_url: str,
    cookies: list[dict[str, str]],
    *,
    max_posts: int,
    max_scrolls: int,
    min_delay: float,
    max_delay: float,
    headless: bool = False,
) -> list[dict[str, str]]:
    if min_delay <= 0 or max_delay <= 0 or min_delay > max_delay:
        raise ValueError("Delay values must be positive and min-delay cannot exceed max-delay.")

    driver = build_driver(headless=headless)
    posts_by_key: dict[str, dict[str, str]] = {}
    stagnant_rounds = 0

    try:
        login_with_cookies(driver, cookies)
        driver.get(group_url)
        print(f"Opened group URL: {group_url}")
        time.sleep(5)
        close_popups(driver)

        previous_count = 0

        for scroll_index in range(max_scrolls):
            expand_see_more(driver)
            expand_post_see_more(driver)
            message_nodes = find_post_message_nodes(driver)

            for message_node in message_nodes:
                try:
                    record = extract_post_record_from_message_node(
                        driver,
                        message_node,
                        group_url,
                    )
                except Exception:  # pragma: no cover
                    continue
                if record:
                    posts_by_key.setdefault(record["post_key"], record)

            print(
                f"Scroll {scroll_index + 1}/{max_scrolls}: "
                f"found {len(message_nodes)} candidate message nodes, "
                f"collected {len(posts_by_key)} unique post bodies"
            )
            if len(posts_by_key) >= max_posts:
                break

            if len(posts_by_key) == previous_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                previous_count = len(posts_by_key)

            if stagnant_rounds >= 3:
                print("No new post bodies detected after several scrolls, stopping early.")
                break

            scroll_amount = random.randint(900, 1600)
            driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_amount)
            random_pause(min_delay, max_delay, scroll_index)

        if not posts_by_key:
            screenshot_path, html_path = dump_debug(
                driver, "scrape_features/post_bodies/debug/group_post_body_scraper_empty"
            )
            raise RuntimeError(
                "No post bodies were collected. "
                f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
            )

        return list(posts_by_key.values())[:max_posts]
    finally:
        driver.quit()


def scrape_multiple_groups_post_bodies(
    group_urls: list[str],
    cookies: list[dict[str, str]],
    *,
    output_path: str | Path | None = None,
    max_posts: int,
    max_scrolls: int,
    min_delay: float,
    max_delay: float,
    headless: bool = False,
) -> list[dict[str, str]]:
    all_posts: dict[str, dict[str, str]] = {}
    failed_groups: list[tuple[str, str]] = []
    resolved_output_path = Path(output_path).resolve() if output_path is not None else None

    for index, group_url in enumerate(group_urls, start=1):
        print(f"Starting group {index}/{len(group_urls)}: {group_url}")
        try:
            group_posts = scrape_group_post_bodies(
                group_url,
                cookies,
                max_posts=max_posts,
                max_scrolls=max_scrolls,
                min_delay=min_delay,
                max_delay=max_delay,
                headless=headless,
            )
        except Exception as exc:
            failed_groups.append((group_url, str(exc)))
            print(f"Failed group {group_url}: {exc}")
            continue

        new_posts = 0
        for post in group_posts:
            if post["post_key"] in all_posts:
                continue
            all_posts[post["post_key"]] = post
            new_posts += 1

        print(
            f"Finished group {index}/{len(group_urls)}: kept {new_posts} new posts, "
            f"{len(all_posts)} unique post bodies total"
        )

        if resolved_output_path is not None and all_posts:
            write_posts_to_csv(list(all_posts.values()), resolved_output_path)
            print(f"Saved interim results to {resolved_output_path}")

    if failed_groups:
        print("Finished with failed groups:")
        for group_url, error_message in failed_groups:
            print(f"- {group_url}: {error_message}")

    return list(all_posts.values())


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    group_urls = normalize_group_urls(args.group_urls)
    if not group_urls:
        group_urls = [DEFAULT_GROUP_URL.rstrip("/")]

    posts = scrape_multiple_groups_post_bodies(
        group_urls,
        cookies,
        output_path=args.output,
        max_posts=args.max_posts,
        max_scrolls=args.max_scrolls,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        headless=args.headless,
    )
    if not posts:
        raise SystemExit("No post bodies were collected from any group.")

    write_posts_to_csv(posts, args.output)
    print(
        f"Saved {len(posts)} post bodies from {len(group_urls)} group(s) to {Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
