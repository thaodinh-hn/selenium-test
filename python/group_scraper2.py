from __future__ import annotations

import argparse
import csv
import hashlib
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from main import build_driver, convert_raw_cookie, login_with_cookies as shared_login_with_cookies


DEFAULT_GROUP_URL = "https://www.facebook.com/groups/1250416722544463/"


def clean_text(value: str) -> str:
    return " ".join(value.split())


def build_post_key(post_url: str, author: str, content: str) -> str:
    normalized_url = clean_text(post_url)
    normalized_author = clean_text(author)
    normalized_content = clean_text(content)
    source = normalized_url or f"{normalized_author}::{normalized_content[:200]}"
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def write_posts_to_csv(posts: list[dict[str, str]], output_path: str | Path) -> None:
    fieldnames = [
        "post_key",
        "author",
        "content",
        "post_url",
        "group_url",
        "scraped_at_utc",
    ]
    with Path(output_path).open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(posts)


def normalize_group_urls(group_urls: list[str] | None) -> list[str]:
    values = group_urls or [DEFAULT_GROUP_URL]
    seen: set[str] = set()
    normalized: list[str] = []

    for value in values:
        url = value.strip().rstrip("/")
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        normalized.append(url)

    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scroll one or more Facebook groups and export visible post content to CSV."
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
        default="group_posts.csv",
        help="CSV file to write scraped posts to.",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=30,
        help="Stop after collecting this many unique posts per group.",
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


def login_with_cookies(driver, cookies: list[dict[str, str]]) -> None:
    shared_login_with_cookies(driver, cookies)


def close_popups(driver) -> None:
    from selenium.webdriver.common.by import By

    dismiss_xpath = (
        "//div[@aria-label='Close' or @aria-label='Đóng' or @aria-label='Not Now' or @aria-label='Lúc khác']"
        "|//span[normalize-space()='Close' or normalize-space()='Đóng' or normalize-space()='Not Now' or normalize-space()='Lúc khác']"
        "/ancestor::*[@role='button'][1]"
    )
    for button in driver.find_elements(By.XPATH, dismiss_xpath):
        try:
            if button.is_displayed():
                button.click()
                time.sleep(1)
        except Exception:  # pragma: no cover
            continue


def expand_see_more(driver) -> None:
    from selenium.webdriver.common.by import By

    more_xpath = (
        "//div[@role='article']//*[self::div or self::span][normalize-space()='See more' or normalize-space()='Xem thêm']"
        "/ancestor::*[@role='button'][1]"
        "|//div[@role='article']//*[@role='button'][.//span[normalize-space()='See more' or normalize-space()='Xem thêm']]"
    )
    for button in driver.find_elements(By.XPATH, more_xpath):
        try:
            if button.is_displayed():
                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.3)
        except Exception:  # pragma: no cover
            continue


def extract_author(post) -> str:
    from selenium.webdriver.common.by import By

    author_xpath = (
        ".//h2//strong//span"
        "|.//h3//strong//span"
        "|.//strong//span"
        "|.//a[@role='link']//strong//span"
    )
    for node in post.find_elements(By.XPATH, author_xpath):
        text = clean_text(node.text)
        if text:
            return text
    return ""


def extract_post_url(post) -> str:
    from selenium.webdriver.common.by import By

    for link in post.find_elements(By.XPATH, ".//a[@href]"):
        href = (link.get_attribute("href") or "").strip()
        if not href:
            continue
        if "/posts/" in href or "/permalink/" in href or "story_fbid=" in href:
            return href.split("?")[0]
    return ""


def extract_post_content(post, author: str) -> str:
    from selenium.webdriver.common.by import By

    primary_nodes = post.find_elements(By.XPATH, ".//div[@data-ad-preview='message']")
    texts = [clean_text(node.text) for node in primary_nodes if clean_text(node.text)]
    if texts:
        return "\n".join(dict.fromkeys(texts))

    fallback_nodes = post.find_elements(By.XPATH, ".//div[@dir='auto'] | .//span[@dir='auto']")
    collected: list[str] = []
    seen: set[str] = set()
    ignored = {clean_text(author), "Like", "Reply", "Share", "Comment", "Thích", "Trả lời"}

    for node in fallback_nodes:
        text = clean_text(node.text)
        if not text or text in ignored or len(text) < 2 or text in seen:
            continue
        seen.add(text)
        collected.append(text)

    return "\n".join(collected[:20])


def extract_post_record(post, group_url: str) -> dict[str, str] | None:
    author = extract_author(post)
    content = extract_post_content(post, author)
    post_url = extract_post_url(post)

    if not author and not content:
        return None

    return {
        "post_key": build_post_key(post_url, author, content),
        "author": author,
        "content": content,
        "post_url": post_url,
        "group_url": group_url,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def find_post_elements(driver):
    from selenium.webdriver.common.by import By

    xpath = "//div[@role='article']"
    return driver.find_elements(By.XPATH, xpath)


def random_pause(min_delay: float, max_delay: float, scroll_index: int) -> None:
    time.sleep(random.uniform(min_delay, max_delay))
    if scroll_index % 4 == 3:
        time.sleep(random.uniform(min_delay, max_delay + 1.5))


def dump_debug(driver, prefix: str) -> tuple[Path, Path]:
    screenshot_path = Path(f"{prefix}.png").resolve()
    html_path = Path(f"{prefix}.html").resolve()
    driver.save_screenshot(str(screenshot_path))
    html_path.write_text(driver.page_source, encoding="utf-8")
    return screenshot_path, html_path


def scrape_group_posts(
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

            for post in find_post_elements(driver):
                try:
                    record = extract_post_record(post, group_url)
                except Exception:  # pragma: no cover
                    continue
                if record:
                    posts_by_key.setdefault(record["post_key"], record)

            print(
                f"Scroll {scroll_index + 1}/{max_scrolls}: collected {len(posts_by_key)} unique posts"
            )
            if len(posts_by_key) >= max_posts:
                break

            if len(posts_by_key) == previous_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                previous_count = len(posts_by_key)

            if stagnant_rounds >= 3:
                print("No new posts detected after several scrolls, stopping early.")
                break

            scroll_amount = random.randint(900, 1600)
            driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_amount)
            random_pause(min_delay, max_delay, scroll_index)

        if not posts_by_key:
            screenshot_path, html_path = dump_debug(driver, "group_scraper_empty")
            raise RuntimeError(
                "No posts were collected. "
                f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
            )

        return list(posts_by_key.values())[:max_posts]
    finally:
        driver.quit()


def scrape_multiple_groups(
    group_urls: list[str],
    cookies: list[dict[str, str]],
    *,
    max_posts: int,
    max_scrolls: int,
    min_delay: float,
    max_delay: float,
    headless: bool = False,
) -> list[dict[str, str]]:
    all_posts: dict[str, dict[str, str]] = {}

    for index, group_url in enumerate(group_urls, start=1):
        print(f"Starting group {index}/{len(group_urls)}: {group_url}")
        group_posts = scrape_group_posts(
            group_url,
            cookies,
            max_posts=max_posts,
            max_scrolls=max_scrolls,
            min_delay=min_delay,
            max_delay=max_delay,
            headless=headless,
        )
        for post in group_posts:
            all_posts.setdefault(post["post_key"], post)

    return list(all_posts.values())


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    group_urls = normalize_group_urls(args.group_urls)
    if not group_urls:
        raise SystemExit("No valid group URLs were provided.")

    posts = scrape_multiple_groups(
        group_urls,
        cookies,
        max_posts=args.max_posts,
        max_scrolls=args.max_scrolls,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        headless=args.headless,
    )
    write_posts_to_csv(posts, args.output)
    print(
        f"Saved {len(posts)} posts from {len(group_urls)} group(s) to {Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
