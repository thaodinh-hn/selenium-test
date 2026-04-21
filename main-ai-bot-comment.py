from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Any

from main import build_driver, convert_raw_cookie
from scrape_features.group_posts.scraper import clean_text, dump_debug, login_with_cookies


DEBUG_OUTPUT_PREFIX = "scrape_features/comment_replies/debug/manual_comment"

COMMENT_EDITOR_XPATHS = [
    (
        "//*[@role='textbox' and @contenteditable='true' and ("
        "contains(@aria-label, 'Viết bình luận')"
        " or contains(@aria-label, 'Write a comment')"
        " or contains(@aria-label, 'Write a public comment')"
        " or contains(@aria-label, 'Viết câu trả lời')"
        " or contains(@aria-label, 'Write a reply')"
        " or contains(@aria-placeholder, 'Viết bình luận')"
        " or contains(@aria-placeholder, 'Write a comment')"
        " or contains(@aria-placeholder, 'Viết câu trả lời')"
        " or contains(@aria-placeholder, 'Write a reply')"
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
AI_SUFFIX = "Do not include emojis or any introductory phrases or additional text."


class CommentBotError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Log in to Facebook with cookies and prepare or publish a single comment on a target post URL."
        )
    )
    parser.add_argument(
        "--cookie-file",
        default="fb_cookie.txt",
        help="Path to a raw Facebook cookie string file.",
    )
    parser.add_argument(
        "--post-url",
        required=True,
        help="Facebook post URL where the comment should be added.",
    )

    comment_group = parser.add_mutually_exclusive_group(required=True)
    comment_group.add_argument(
        "--comment",
        help="Inline comment content.",
    )
    comment_group.add_argument(
        "--comment-file",
        help="Path to a UTF-8 text file containing the comment content.",
    )
    comment_group.add_argument(
        "--use-ai",
        action="store_true",
        help="Generate comment content from OpenAI using OPENAI_* env vars or the --ai-* flags.",
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually submit the comment. Without this flag, the script stops after filling the editor.",
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
        help="Maximum seconds to wait for Facebook UI elements.",
    )
    parser.add_argument(
        "--page-load-wait",
        type=float,
        default=5.0,
        help="Seconds to wait after opening the post page.",
    )
    parser.add_argument(
        "--debug-editor-scan",
        action="store_true",
        help="Print each find_comment_editor scan step, including matched elements and aria labels.",
    )
    parser.add_argument(
        "--ai-model",
        default=os.getenv("OPENAI_MODEL", ""),
        help="OpenAI model to use when --use-ai is enabled.",
    )
    parser.add_argument(
        "--ai-prompt",
        default=os.getenv("OPENAI_PROMPT", ""),
        help="Prompt used to generate comment content when --use-ai is enabled.",
    )
    return parser.parse_args()


def resolve_comment_text(comment: str | None, comment_file: str | None) -> str:
    if comment_file:
        content = Path(comment_file).read_text(encoding="utf-8")
    elif comment is not None:
        content = comment
    else:  # pragma: no cover
        raise ValueError("Either comment or comment_file must be provided.")

    normalized = content.replace("\r\n", "\n").strip()
    if not clean_text(normalized):
        raise ValueError("Comment content is empty.")

    return normalized


def build_ai_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    if not normalized:
        raise ValueError("OPENAI_PROMPT or --ai-prompt is required when --use-ai is enabled.")

    if AI_SUFFIX in normalized:
        return normalized
    return f"{normalized}\n{AI_SUFFIX}"


def generate_ai_comment(prompt: str, model: str) -> str:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required when --use-ai is enabled.")
    if not model.strip():
        raise ValueError("OPENAI_MODEL or --ai-model is required when --use-ai is enabled.")

    final_prompt = build_ai_prompt(prompt)

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "openai package is not installed. Install it before using --use-ai."
        ) from exc

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=final_prompt,
    )
    comment = clean_text((response.output_text or "").strip())
    if not comment:
        raise RuntimeError("OpenAI returned an empty comment.")
    return comment


def resolve_runtime_comment(args: argparse.Namespace) -> str:
    if args.use_ai:
        return generate_ai_comment(args.ai_prompt, args.ai_model)
    return resolve_comment_text(args.comment, args.comment_file)


def wait_for_element(driver: Any, xpaths: list[str], *, timeout: float, label: str) -> Any:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in xpaths:
            for element in driver.find_elements("xpath", xpath):
                try:
                    if element.is_displayed():
                        return element
                except Exception:  # pragma: no cover
                    continue
        time.sleep(0.5)

    screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_{label}")
    raise CommentBotError(
        f"Could not find {label}. Current URL: {driver.current_url}. "
        f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
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


def is_login_required(driver: Any) -> bool:
    return bool(driver.find_elements("xpath", "//input[@name='email' or @name='pass']"))


def looks_like_post_url(url: str) -> bool:
    return bool(POST_URL_HINT_PATTERN.search(url))


def ensure_post_context(driver: Any, expected_post_url: str) -> None:
    current_url = clean_text(driver.current_url)
    if not current_url:
        raise CommentBotError("Browser has empty current URL.")
    if is_login_required(driver):
        raise CommentBotError(
            "Facebook redirected to login page; cookie session is not active."
        )
    if looks_like_post_url(expected_post_url) and not looks_like_post_url(current_url):
        raise CommentBotError(
            f"Expected post URL but browser was redirected to: {current_url}"
        )


def click_comment_trigger_if_available(driver: Any, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in COMMENT_TRIGGER_XPATHS:
            for button in driver.find_elements("xpath", xpath):
                try:
                    if not button.is_displayed():
                        continue
                    click_element(driver, button)
                    return
                except Exception:  # pragma: no cover
                    continue
        time.sleep(0.3)


def dismiss_blocking_dialogs(driver: Any) -> None:
    safe_dismiss_xpaths = [
        (
            "//*[@role='button' and ("
            "@aria-label='Not Now' or @aria-label='Lúc khác'"
            " or @aria-label='Bỏ qua' or @aria-label='Skip'"
            ")]"
        ),
        (
            "//span[normalize-space()='Not Now' or normalize-space()='Lúc khác'"
            " or normalize-space()='Bỏ qua' or normalize-space()='Skip']"
            "/ancestor::*[@role='button'][1]"
        ),
    ]

    for xpath in safe_dismiss_xpaths:
        for button in driver.find_elements("xpath", xpath):
            try:
                if not button.is_displayed():
                    continue
                click_element(driver, button)
                time.sleep(1)
                return
            except Exception:  # pragma: no cover
                continue


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


def truncate_debug_value(value: str, *, limit: int = 100) -> str:
    normalized = clean_text(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 3]}..."


def describe_editor_candidate(element: Any) -> str:
    try:
        aria_label = element.get_attribute("aria-label") or ""
    except Exception:
        aria_label = ""
    try:
        aria_placeholder = element.get_attribute("aria-placeholder") or ""
    except Exception:
        aria_placeholder = ""
    try:
        text = get_editor_text(element)
    except Exception:
        text = ""

    return (
        f"label='{truncate_debug_value(aria_label)}' "
        f"placeholder='{truncate_debug_value(aria_placeholder)}' "
        f"text='{truncate_debug_value(text)}'"
    )


def debug_editor_scan(message: str, *, enabled: bool) -> None:
    if enabled:
        print(f"[find_comment_editor] {message}")


def find_comment_editor(driver: Any, *, timeout: float, debug_scan: bool = False) -> Any:
    deadline = time.time() + timeout
    scan_count = 0
    while time.time() < deadline:
        scan_count += 1
        debug_editor_scan(
            f"scan #{scan_count} start; current_url={getattr(driver, 'current_url', '<unknown>')}",
            enabled=debug_scan,
        )
        candidates: list[Any] = []
        reply_candidates: list[Any] = []
        for xpath_index, xpath in enumerate(COMMENT_EDITOR_XPATHS, start=1):
            elements = driver.find_elements("xpath", xpath)
            debug_editor_scan(
                f"xpath #{xpath_index} matched {len(elements)} elements: {xpath}",
                enabled=debug_scan,
            )
            for element_index, element in enumerate(elements, start=1):
                try:
                    displayed = element.is_displayed()
                    reply_editor = is_reply_editor(element)
                    comment_editor = looks_like_comment_editor(element)
                    debug_editor_scan(
                        (
                            f"element #{element_index}: displayed={displayed} "
                            f"reply={reply_editor} comment_like={comment_editor} "
                            f"{describe_editor_candidate(element)}"
                        ),
                        enabled=debug_scan,
                    )
                    if not displayed:
                        continue
                    if reply_editor:
                        reply_candidates.append(element)
                        continue
                    candidates.append(element)
                except Exception as exc:  # pragma: no cover
                    debug_editor_scan(
                        f"element #{element_index}: skipped due to {type(exc).__name__}: {exc}",
                        enabled=debug_scan,
                    )
                    continue

        for candidate in candidates:
            try:
                if looks_like_comment_editor(candidate):
                    debug_editor_scan(
                        f"selected comment-like editor: {describe_editor_candidate(candidate)}",
                        enabled=debug_scan,
                    )
                    return candidate
            except Exception as exc:  # pragma: no cover
                debug_editor_scan(
                    f"comment-like check failed with {type(exc).__name__}: {exc}",
                    enabled=debug_scan,
                )
                continue

        if candidates:
            debug_editor_scan(
                f"selected first visible non-reply candidate: {describe_editor_candidate(candidates[0])}",
                enabled=debug_scan,
            )
            return candidates[0]
        if reply_candidates:
            debug_editor_scan(
                f"selected reply fallback candidate: {describe_editor_candidate(reply_candidates[0])}",
                enabled=debug_scan,
            )
            return reply_candidates[0]
        debug_editor_scan("no visible editor candidates found; sleeping 0.4s", enabled=debug_scan)
        time.sleep(0.4)

    screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_comment_editor")
    raise CommentBotError(
        f"Could not find comment editor. Current URL: {driver.current_url}. "
        f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
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


def fill_comment_editor_with_keys(driver: Any, editor: Any, comment_text: str) -> None:
    from selenium.webdriver import ActionChains
    from selenium.webdriver.common.keys import Keys

    click_element(driver, editor)
    ActionChains(driver).click(editor).perform()

    for modifier in (Keys.COMMAND, Keys.CONTROL):
        try:
            ActionChains(driver).key_down(modifier).send_keys("a").key_up(modifier).perform()
            break
        except Exception:
            continue

    editor.send_keys(Keys.BACKSPACE)

    lines = comment_text.split("\n")
    for index, line in enumerate(lines):
        if line:
            editor.send_keys(line)
        if index != len(lines) - 1:
            ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()


def get_editor_text(editor: Any) -> str:
    text = editor.get_attribute("textContent") or ""
    if not text.strip():
        text = editor.text or ""
    return text


def compact_text(value: str) -> str:
    return "".join(value.split())


def editor_contains_comment(editor: Any, comment_text: str) -> bool:
    expected = clean_text(comment_text)
    actual = clean_text(get_editor_text(editor))
    if not expected:
        return False
    if expected == actual or expected in actual:
        return True
    compact_expected = compact_text(comment_text)
    compact_actual = compact_text(get_editor_text(editor))
    return bool(compact_expected and (compact_expected == compact_actual or compact_expected in compact_actual))


def submit_comment(editor: Any) -> None:
    from selenium.webdriver.common.keys import Keys

    editor.send_keys(Keys.ENTER)


def comment_on_post(
    post_url: str,
    comment_text: str,
    cookies: list[dict[str, str]],
    *,
    publish: bool,
    headless: bool,
    timeout: float,
    page_load_wait: float,
    debug_editor_scan: bool,
) -> str:
    driver = build_driver(headless=headless)

    try:
        login_with_cookies(driver, cookies)
        driver.get(post_url)
        time.sleep(page_load_wait)
        ensure_post_context(driver, post_url)

        dismiss_blocking_dialogs(driver)
        ensure_post_context(driver, post_url)
        click_comment_trigger_if_available(driver, timeout=min(timeout, 5.0))
        dismiss_blocking_dialogs(driver)
        ensure_post_context(driver, post_url)
        editor = find_comment_editor(driver, timeout=timeout, debug_scan=debug_editor_scan)
        fill_comment_editor(driver, editor, comment_text)
        time.sleep(1)

        dismiss_blocking_dialogs(driver)
        ensure_post_context(driver, post_url)
        editor = find_comment_editor(
            driver,
            timeout=min(timeout, 6.0),
            debug_scan=debug_editor_scan,
        )
        if not editor_contains_comment(editor, comment_text):
            debug_editor_scan("JS insert mismatch; retrying with keyboard input", enabled=debug_editor_scan)
            fill_comment_editor_with_keys(driver, editor, comment_text)
            time.sleep(1)
            editor = find_comment_editor(
                driver,
                timeout=min(timeout, 6.0),
                debug_scan=debug_editor_scan,
            )

        if not editor_contains_comment(editor, comment_text):
            screenshot_path, html_path = dump_debug(
                driver,
                f"{DEBUG_OUTPUT_PREFIX}_editor_text_mismatch",
            )
            raise CommentBotError(
                "The comment editor was found, but the comment text was not inserted correctly. "
                f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
            )

        if not publish:
            return "dry-run"

        submit_comment(editor)
        time.sleep(3)
        return "published"
    finally:
        driver.quit()


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    comment_text = resolve_runtime_comment(args)
    status = comment_on_post(
        args.post_url,
        comment_text,
        cookies,
        publish=args.publish,
        headless=args.headless,
        timeout=args.timeout,
        page_load_wait=args.page_load_wait,
        debug_editor_scan=args.debug_editor_scan,
    )
    print(f"Comment status: {status}")
    if status == "dry-run":
        print("Editor was filled successfully. Re-run with --publish to submit the comment.")


if __name__ == "__main__":
    main()
