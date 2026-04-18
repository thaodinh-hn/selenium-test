from __future__ import annotations

import argparse
import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from main import build_driver, convert_raw_cookie
from scrape_features.group_posts.scraper import clean_text, dump_debug, login_with_cookies


DEBUG_OUTPUT_PREFIX = "scrape_features/comment_replies/debug/comment_executor"

COMMENT_EDITOR_XPATHS = [
    (
        "//*[@role='textbox' and @contenteditable='true' and ("
        "contains(@aria-label, 'Viết bình luận')"
        " or contains(@aria-label, 'Write a comment')"
        " or contains(@aria-label, 'Write a public comment')"
        " or contains(@aria-placeholder, 'Viết bình luận')"
        " or contains(@aria-placeholder, 'Write a comment')"
        ")]"
    ),
    "//*[@role='textbox' and @contenteditable='true']",
]

COMMENT_TRIGGER_XPATHS = [
    (
        "//*[@role='button' and ("
        "contains(@aria-label, 'Bình luận')"
        " or contains(@aria-label, 'Comment')"
        ")]"
    ),
    (
        "//*[@role='button'][.//*[self::span or self::div]["
        "normalize-space()='Bình luận' or normalize-space()='Comment'"
        "]]"
    ),
]

POST_URL_HINT_PATTERN = re.compile(r"/posts/|story_fbid=|/permalink/")


class CommentExecutionError(RuntimeError):
    def __init__(self, status_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read a generated comment plan CSV and attempt to comment on each post URL. "
            "Dry-run mode updates status without clicking submit."
        )
    )
    parser.add_argument(
        "--cookie-file",
        default="fb_cookie.txt",
        help="Path to a raw Facebook cookie string file.",
    )
    parser.add_argument(
        "--plan-file",
        default="scrape_features/comment_replies/data/comment_plan.csv",
        help="CSV file created by generate_plan.py.",
    )
    parser.add_argument(
        "--result-file",
        default="scrape_features/comment_replies/data/comment_results.csv",
        help="CSV file where execution status will be written.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually submit comments. Without this flag, script runs dry-run only.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Maximum seconds to wait for UI elements.",
    )
    parser.add_argument(
        "--page-load-wait",
        type=float,
        default=5.0,
        help="Seconds to wait after opening each post URL.",
    )
    parser.add_argument(
        "--delay-between-posts",
        type=float,
        default=2.0,
        help="Seconds to wait between handling posts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of rows to execute (0 = all pending rows).",
    )
    parser.add_argument(
        "--only-pending",
        action="store_true",
        help="Process only rows with status 'pending'.",
    )
    return parser.parse_args()


def wait_for_element(driver: Any, xpaths: list[str], *, timeout: float, label: str):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in xpaths:
            elements = driver.find_elements("xpath", xpath)
            for element in elements:
                try:
                    if element.is_displayed():
                        return element
                except Exception:  # pragma: no cover
                    continue
        time.sleep(0.5)

    screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_{label}")
    raise RuntimeError(
        f"Could not find {label}. Current URL: {driver.current_url}. "
        f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
    )


def is_login_required(driver: Any) -> bool:
    login_inputs = driver.find_elements("xpath", "//input[@name='email' or @name='pass']")
    return bool(login_inputs)


def looks_like_post_url(url: str) -> bool:
    return bool(POST_URL_HINT_PATTERN.search(url))


def ensure_post_context(driver: Any, expected_post_url: str) -> None:
    current_url = clean_text(driver.current_url)
    if not current_url:
        raise CommentExecutionError("redirected_or_unavailable_post", "Browser has empty current URL.")
    if is_login_required(driver):
        raise CommentExecutionError(
            "redirected_or_unavailable_post",
            "Facebook redirected to login page; cookie session is not active.",
        )
    if looks_like_post_url(expected_post_url) and not looks_like_post_url(current_url):
        raise CommentExecutionError(
            "redirected_or_unavailable_post",
            f"Expected post URL but browser was redirected to: {current_url}",
        )


def click_element(driver: Any, element: Any) -> None:
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        element,
    )
    try:
        element.click()
        return
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def click_comment_trigger_if_available(driver: Any, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in COMMENT_TRIGGER_XPATHS:
            buttons = driver.find_elements("xpath", xpath)
            for button in buttons:
                try:
                    if not button.is_displayed():
                        continue
                    click_element(driver, button)
                    return
                except Exception:  # pragma: no cover
                    continue
        time.sleep(0.3)


def is_reply_editor(editor: Any) -> bool:
    aria_label = clean_text(editor.get_attribute("aria-label") or "").lower()
    aria_placeholder = clean_text(editor.get_attribute("aria-placeholder") or "").lower()
    combined = f"{aria_label} {aria_placeholder}"
    return "trả lời" in combined or "reply" in combined


def looks_like_comment_editor(editor: Any) -> bool:
    aria_label = clean_text(editor.get_attribute("aria-label") or "").lower()
    aria_placeholder = clean_text(editor.get_attribute("aria-placeholder") or "").lower()
    combined = f"{aria_label} {aria_placeholder}"
    return "bình luận" in combined or "comment" in combined


def find_comment_editor(driver: Any, *, timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidates: list[Any] = []
        for xpath in COMMENT_EDITOR_XPATHS:
            for element in driver.find_elements("xpath", xpath):
                try:
                    if not element.is_displayed():
                        continue
                    if is_reply_editor(element):
                        continue
                    candidates.append(element)
                except Exception:  # pragma: no cover
                    continue

        for candidate in candidates:
            try:
                if looks_like_comment_editor(candidate):
                    return candidate
            except Exception:  # pragma: no cover
                continue
        if candidates:
            return candidates[0]
        time.sleep(0.4)

    screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_comment_editor")
    raise CommentExecutionError(
        "comment_editor_not_found",
        f"Could not find comment_editor. Current URL: {driver.current_url}. "
        f"Saved screenshot to {screenshot_path} and HTML to {html_path}.",
    )


def fill_comment_editor(driver: Any, editor: Any, comment_text: str) -> None:
    driver.execute_script(
        """
        const element = arguments[0];
        const text = arguments[1];
        element.focus();
        if (document.activeElement !== element) {
            element.click();
        }
        if (document.execCommand) {
            try {
                document.execCommand('selectAll', false, null);
                if (document.execCommand('insertText', false, text)) {
                    return;
                }
            } catch (error) {}
        }
        element.textContent = text;
        element.dispatchEvent(new InputEvent('input', {
            bubbles: true,
            inputType: 'insertText',
            data: text,
        }));
        element.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        editor,
        comment_text,
    )


def editor_contains_comment(editor: Any, comment_text: str) -> bool:
    expected = clean_text(comment_text)
    actual = clean_text(editor.get_attribute("textContent") or "")
    if not expected:
        return False
    return expected == actual or expected in actual


def submit_comment(editor: Any) -> None:
    from selenium.webdriver.common.keys import Keys

    editor.send_keys(Keys.ENTER)


def read_plan_rows(plan_path: Path) -> list[dict[str, str]]:
    with plan_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_result_rows(result_path: Path, rows: list[dict[str, str]]) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "post_key",
        "post_url",
        "author",
        "content_excerpt",
        "generated_comment",
        "status",
        "error",
        "commented_at_utc",
    ]
    with result_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def should_process(row: dict[str, str], *, only_pending: bool) -> bool:
    if not only_pending:
        return True
    return clean_text(row.get("status", "").lower()) in {"", "pending"}


def execute_comment_plan(
    rows: list[dict[str, str]],
    cookies: list[dict[str, str]],
    *,
    publish: bool,
    headless: bool,
    timeout: float,
    page_load_wait: float,
    delay_between_posts: float,
    limit: int,
    only_pending: bool,
) -> list[dict[str, str]]:
    driver = build_driver(headless=headless)
    processed_count = 0

    try:
        login_with_cookies(driver, cookies)

        for row in rows:
            if not should_process(row, only_pending=only_pending):
                continue
            if limit > 0 and processed_count >= limit:
                break

            post_url = clean_text(row.get("post_url", ""))
            comment_text = (row.get("generated_comment") or "").strip()
            if not post_url or not comment_text:
                row["status"] = "skipped"
                row["error"] = "Missing post_url or generated_comment."
                row["commented_at_utc"] = ""
                continue

            try:
                driver.get(post_url)
                time.sleep(page_load_wait)
                ensure_post_context(driver, post_url)
                click_comment_trigger_if_available(driver, timeout=min(timeout, 6.0))

                editor = find_comment_editor(driver, timeout=timeout)
                click_element(driver, editor)
                fill_comment_editor(driver, editor, comment_text)
                if not editor_contains_comment(editor, comment_text):
                    raise CommentExecutionError(
                        "comment_editor_not_found",
                        "Comment editor was found but text did not appear after fill attempt.",
                    )

                if publish:
                    try:
                        submit_comment(editor)
                    except Exception as exc:
                        raise CommentExecutionError(
                            "submit_failed",
                            f"Failed to submit comment: {exc}",
                        ) from exc
                    row["status"] = "commented"
                else:
                    row["status"] = "dry_run_ready"

                row["error"] = ""
                row["commented_at_utc"] = datetime.now(timezone.utc).isoformat()
            except CommentExecutionError as exc:
                row["status"] = exc.status_code
                row["error"] = str(exc)
                row["commented_at_utc"] = ""
            except Exception as exc:
                row["status"] = "failed_unexpected"
                row["error"] = str(exc)
                row["commented_at_utc"] = ""

            processed_count += 1
            if delay_between_posts > 0:
                time.sleep(delay_between_posts)
    finally:
        driver.quit()

    return rows


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    plan_path = Path(args.plan_file).resolve()
    if not plan_path.exists():
        raise SystemExit(f"Plan file not found: {plan_path}")

    rows = read_plan_rows(plan_path)
    if not rows:
        raise SystemExit(f"Plan file has no rows: {plan_path}")

    result_rows = execute_comment_plan(
        rows,
        cookies,
        publish=args.publish,
        headless=args.headless,
        timeout=args.timeout,
        page_load_wait=args.page_load_wait,
        delay_between_posts=args.delay_between_posts,
        limit=args.limit,
        only_pending=args.only_pending,
    )
    result_path = Path(args.result_file).resolve()
    write_result_rows(result_path, result_rows)
    print(f"Saved execution results to {result_path}")


if __name__ == "__main__":
    main()
