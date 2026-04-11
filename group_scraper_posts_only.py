from __future__ import annotations

import argparse
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from group_scraper import (
    DEFAULT_GROUP_URL,
    build_post_key,
    clean_text,
    close_popups,
    dump_debug,
    expand_see_more,
    extract_author,
    extract_post_url,
    login_with_cookies,
    normalize_group_urls,
    random_pause,
    write_posts_to_csv,
)
from main import build_driver, convert_raw_cookie


STRICT_MESSAGE_XPATH = (
    ".//*[@data-ad-preview='message']"
    "|.//*[@data-ad-comet-preview='message']"
    "|.//*[@data-ad-rendering-role='story_message']"
)

MESSAGE_ELEMENT_XPATH = (
    "//*[@data-ad-preview='message'"
    " or @data-ad-comet-preview='message'"
    " or @data-ad-rendering-role='story_message']"
)

POST_CONTEXT_XPATH = (
    "./ancestor::div[.//a[contains(@href,'/posts/')"
    " or contains(@href,'story_fbid=')"
    " or contains(@href,'/permalink/')]][1]"
)


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


def extract_post_content_only(post) -> str:
    from selenium.webdriver.common.by import By

    nodes = post.find_elements(By.XPATH, STRICT_MESSAGE_XPATH)
    texts = [node.text for node in nodes if clean_text(node.text)]
    return merge_content_blocks(texts)


def find_story_message_elements(driver):
    from selenium.webdriver.common.by import By

    return driver.find_elements(By.XPATH, MESSAGE_ELEMENT_XPATH)


def find_post_context_from_message(message):
    try:
        return message.find_element("xpath", POST_CONTEXT_XPATH)
    except Exception:
        return message


def extract_post_record_only(message, group_url: str) -> dict[str, str] | None:
    content = extract_post_content_only(message)
    context = find_post_context_from_message(message)
    author = extract_author(context)
    post_url = extract_post_url(context)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scroll Facebook groups and export only the main post body, excluding comments."
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
        default="group_posts_only.csv",
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


def scrape_group_posts_only(
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

            for post in find_story_message_elements(driver):
                try:
                    record = extract_post_record_only(post, group_url)
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
            screenshot_path, html_path = dump_debug(driver, "group_scraper_posts_only_empty")
            raise RuntimeError(
                "No post-body content was collected. "
                f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
            )

        return list(posts_by_key.values())[:max_posts]
    finally:
        driver.quit()


def scrape_multiple_groups_only(
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
            group_posts = scrape_group_posts_only(
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
            f"{len(all_posts)} unique posts total"
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

    posts = scrape_multiple_groups_only(
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
