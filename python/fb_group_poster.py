from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from scrape_features.group_posts.scraper import clean_text, close_popups, dump_debug, login_with_cookies
from main import build_driver, convert_raw_cookie


DEBUG_OUTPUT_PREFIX = "scrape_features/group_posts/debug/fb_group_poster"


OPEN_COMPOSER_XPATHS = [
    (
        "//*[@role='button' and ("
        "contains(@aria-label, 'Bạn viết gì đi')"
        " or contains(@aria-label, 'Write something')"
        " or contains(@aria-label, \"What's on your mind\")"
        " or contains(@aria-label, 'Create public post')"
        " or contains(@aria-label, 'Tạo bài viết')"
        ")]"
    ),
    (
        "//span[contains(normalize-space(), 'Bạn viết gì đi')"
        " or contains(normalize-space(), 'Write something')"
        " or contains(normalize-space(), \"What's on your mind\")"
        " or contains(normalize-space(), 'Create public post')"
        " or contains(normalize-space(), 'Tạo bài viết')]"
        "/ancestor::*[@role='button'][1]"
    ),
    (
        "//*[@role='button' and (.//*[self::span or self::div]["
        "contains(normalize-space(), 'Bạn viết gì đi')"
        " or contains(normalize-space(), 'Write something')"
        " or contains(normalize-space(), \"What's on your mind\")"
        " or contains(normalize-space(), 'Create public post')"
        " or contains(normalize-space(), 'Tạo bài viết')"
        "])]"
    ),
]

POST_DIALOG_XPATHS = [
    "//*[@role='dialog' and (@aria-label='Tạo bài viết' or @aria-label='Create post' or @aria-label='Create public post')]",
    (
        "//*[@role='dialog' and (.//*[self::h1 or self::h2 or self::span]"
        "[normalize-space()='Tạo bài viết'"
        " or normalize-space()='Create post'"
        " or normalize-space()='Create public post'])]"
    ),
]

GLOBAL_POST_EDITOR_XPATHS = [
    (
        "//*[@contenteditable='true' and @role='textbox' and @data-lexical-editor='true' and ("
        "contains(@aria-placeholder, 'Tạo bài viết')"
        " or contains(@aria-label, 'Tạo bài viết')"
        " or contains(@aria-placeholder, 'Write something')"
        " or contains(@aria-label, 'Write something')"
        " or contains(@aria-placeholder, \"What's on your mind\")"
        " or contains(@aria-label, \"What's on your mind\")"
        " or contains(@aria-placeholder, 'Create public post')"
        " or contains(@aria-label, 'Create public post')"
        ")]"
    ),
    (
        "//*[@contenteditable='true' and @role='textbox' and @data-lexical-editor='true' and not("
        "contains(@aria-placeholder, 'Viết bình luận')"
        " or contains(@aria-label, 'Viết bình luận')"
        " or contains(@aria-placeholder, 'Write a comment')"
        " or contains(@aria-label, 'Write a comment')"
        ")]"
    ),
]

EDITOR_XPATHS = [
    ".//*[@contenteditable='true' and @role='textbox' and @data-lexical-editor='true']",
    (
        ".//*[@contenteditable='true' and @role='textbox' and ("
        "contains(@aria-placeholder, 'Tạo bài viết')"
        " or contains(@aria-placeholder, 'Write something')"
        " or contains(@aria-placeholder, \"What's on your mind\")"
        " or contains(@aria-placeholder, 'Create public post')"
        ")]"
    ),
    ".//*[@contenteditable='true' and @role='textbox']",
    ".//*[@contenteditable='true' and (@role='textbox' or @aria-multiline='true')]",
]

PUBLISH_BUTTON_XPATHS = [
    (
        ".//*[@role='button' and ("
        "@aria-label='Đăng' or @aria-label='Post' or @aria-label='Đăng bài'"
        ")]"
    ),
    (
        ".//*[@role='button']["
        ".//*[self::span or self::div][normalize-space()='Đăng'"
        " or normalize-space()='Post'"
        " or normalize-space()='Đăng bài']"
        "]"
    ),
]

GLOBAL_PUBLISH_BUTTON_XPATHS = [
    "//*[@role='button' and (@aria-label='Đăng' or @aria-label='Post' or @aria-label='Đăng bài')]",
    (
        "//*[@role='button']["
        ".//*[self::span or self::div][normalize-space()='Đăng'"
        " or normalize-space()='Post'"
        " or normalize-space()='Đăng bài']"
        "]"
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log in to Facebook with cookies and create a post in a target group."
    )
    parser.add_argument(
        "--cookie-file",
        default="fb_cookie.txt",
        help="Path to a raw Facebook cookie string file.",
    )
    parser.add_argument(
        "--group-url",
        required=True,
        help="Facebook group URL where the post will be created.",
    )

    message_group = parser.add_mutually_exclusive_group(required=True)
    message_group.add_argument(
        "--message",
        help="Inline post content.",
    )
    message_group.add_argument(
        "--message-file",
        help="Path to a UTF-8 text file containing the post content.",
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually click the publish button. Without this flag the script stops after filling the editor.",
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
        default=6.0,
        help="Seconds to wait after opening the group page.",
    )
    parser.add_argument(
        "--post-submit-wait",
        type=float,
        default=8.0,
        help="Seconds to wait after clicking the publish button.",
    )
    return parser.parse_args()


def resolve_message(message: str | None, message_file: str | None) -> str:
    if message_file:
        content = Path(message_file).read_text(encoding="utf-8")
    elif message is not None:
        content = message
    else:  # pragma: no cover
        raise ValueError("Either message or message_file must be provided.")

    normalized = content.replace("\r\n", "\n").strip()
    if not clean_text(normalized):
        raise ValueError("Post content is empty.")

    return normalized


def contains_non_bmp_characters(value: str) -> bool:
    return any(ord(char) > 0xFFFF for char in value)


def to_bmp_safe_text(value: str) -> str:
    return "".join(char for char in value if ord(char) <= 0xFFFF)


def ensure_logged_in(driver: Any) -> None:
    from selenium.webdriver.common.by import By

    login_inputs = driver.find_elements(By.XPATH, "//input[@name='email' or @name='pass']")
    if login_inputs:
        raise RuntimeError(
            "Facebook session is not logged in. Refresh fb_cookie.txt with a valid logged-in cookie."
        )


def is_enabled(element: Any) -> bool:
    aria_disabled = (element.get_attribute("aria-disabled") or "").strip().lower()
    disabled = (element.get_attribute("disabled") or "").strip().lower()
    return aria_disabled != "true" and disabled not in {"true", "disabled"} and element.is_enabled()


def find_first_matching_element(
    search_context: Any,
    xpaths: list[str],
    *,
    require_enabled: bool = False,
) -> Any | None:
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import StaleElementReferenceException

    try:
        current_context = search_context() if callable(search_context) else search_context
    except StaleElementReferenceException:
        return None

    if current_context is None:
        return None

    for xpath in xpaths:
        try:
            elements = current_context.find_elements(By.XPATH, xpath)
        except StaleElementReferenceException:
            return None

        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                if require_enabled and not is_enabled(element):
                    continue
                return element
            except Exception:  # pragma: no cover
                continue
    return None


def wait_for_element(
    search_context: Any,
    xpaths: list[str],
    *,
    timeout: float,
    label: str,
    require_enabled: bool = False,
    debug_driver: Any | None = None,
) -> Any:
    deadline = time.time() + timeout
    while time.time() < deadline:
        element = find_first_matching_element(
            search_context,
            xpaths,
            require_enabled=require_enabled,
        )
        if element is not None:
            return element
        time.sleep(0.5)

    active_driver = debug_driver or search_context
    screenshot_path, html_path = dump_debug(active_driver, f"{DEBUG_OUTPUT_PREFIX}_{label}")
    raise RuntimeError(
        f"Could not find {label}. "
        f"Current URL: {active_driver.current_url}. "
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
        pass

    driver.execute_script("arguments[0].click();", element)


def open_group_post_composer(driver: Any, *, timeout: float) -> None:
    close_popups(driver)
    button = wait_for_element(
        driver,
        OPEN_COMPOSER_XPATHS,
        timeout=timeout,
        label="open_composer",
    )
    click_element(driver, button)


def build_post_dialog_provider(driver: Any):
    return lambda: find_first_matching_element(driver, POST_DIALOG_XPATHS)


def fill_editor_with_js(driver: Any, editor: Any, message: str) -> None:
    driver.execute_script(
        """
        const element = arguments[0];
        const text = arguments[1];
        element.focus();
        if (document.activeElement !== element) {
            element.click();
        }

        const setSelectionToEnd = () => {
            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(element);
            range.collapse(false);
            selection.removeAllRanges();
            selection.addRange(range);
        };

        const tryExecCommand = () => {
            if (!document.execCommand) {
                return false;
            }
            try {
                setSelectionToEnd();
                element.dispatchEvent(new InputEvent('beforeinput', {
                    bubbles: true,
                    cancelable: true,
                    inputType: 'insertText',
                    data: text,
                }));
                return document.execCommand('insertText', false, text);
            } catch (error) {
                return false;
            }
        };

        if (!tryExecCommand()) {
            element.textContent = text;
            element.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                inputType: 'insertText',
                data: text,
            }));
        }

        element.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        editor,
        message,
    )


def get_editor_text(editor: Any) -> str:
    text = editor.get_attribute("textContent") or ""
    if not text.strip():
        text = editor.text or ""
    return text


def editor_contains_message(editor: Any, message: str) -> bool:
    normalized_message = clean_text(message)
    normalized_editor = clean_text(get_editor_text(editor))
    if not normalized_message:
        return False
    return normalized_message == normalized_editor or normalized_message in normalized_editor


def fill_editor_with_keys(driver: Any, editor: Any, message: str) -> None:
    from selenium.webdriver import ActionChains
    from selenium.webdriver.common.keys import Keys

    safe_message = to_bmp_safe_text(message)
    if safe_message != message:
        print(
            "Message contains characters outside ChromeDriver BMP support. "
            "Fallback typing will omit those characters."
        )

    click_element(driver, editor)
    ActionChains(driver).click(editor).perform()

    for modifier in (Keys.COMMAND, Keys.CONTROL):
        try:
            ActionChains(driver).key_down(modifier).send_keys("a").key_up(modifier).perform()
            break
        except Exception:
            continue

    editor.send_keys(Keys.BACKSPACE)

    lines = safe_message.split("\n")
    for index, line in enumerate(lines):
        if line:
            editor.send_keys(line)
        if index != len(lines) - 1:
            ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()


def wait_for_optional_element(
    search_context: Any,
    xpaths: list[str],
    *,
    timeout: float,
    require_enabled: bool = False,
) -> Any | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        element = find_first_matching_element(
            search_context,
            xpaths,
            require_enabled=require_enabled,
        )
        if element is not None:
            return element
        time.sleep(0.5)
    return None


def fill_post_editor(
    driver: Any,
    message: str,
    *,
    timeout: float,
    require_publish_button: bool,
) -> None:
    dialog_provider = build_post_dialog_provider(driver)
    editor = wait_for_optional_element(
        driver,
        GLOBAL_POST_EDITOR_XPATHS,
        timeout=min(timeout, 6.0),
    )
    if editor is None:
        editor = wait_for_element(
            dialog_provider,
            EDITOR_XPATHS,
            timeout=timeout,
            label="editor",
            debug_driver=driver,
        )
    fill_editor_with_js(driver, editor, message)
    time.sleep(1)
    editor = wait_for_optional_element(
        driver,
        GLOBAL_POST_EDITOR_XPATHS,
        timeout=min(timeout, 4.0),
    ) or wait_for_element(
        dialog_provider,
        EDITOR_XPATHS,
        timeout=timeout,
        label="editor_after_js",
        debug_driver=driver,
    )

    if not editor_contains_message(editor, message):
        editor = wait_for_optional_element(
            driver,
            GLOBAL_POST_EDITOR_XPATHS,
            timeout=min(timeout, 4.0),
        ) or wait_for_element(
            dialog_provider,
            EDITOR_XPATHS,
            timeout=timeout,
            label="editor_before_keys",
            debug_driver=driver,
        )
        fill_editor_with_keys(driver, editor, message)
        time.sleep(1)
        editor = wait_for_optional_element(
            driver,
            GLOBAL_POST_EDITOR_XPATHS,
            timeout=min(timeout, 4.0),
        ) or wait_for_element(
            dialog_provider,
            EDITOR_XPATHS,
            timeout=timeout,
            label="editor_after_keys",
            debug_driver=driver,
        )

    if not editor_contains_message(editor, message):
        screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_editor_text_mismatch")
        raise RuntimeError(
            "The post editor was found, but the message was not inserted into that editor. "
            f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
        )

    if not require_publish_button:
        return

    publish_button = wait_for_optional_element(
        driver,
        GLOBAL_PUBLISH_BUTTON_XPATHS,
        timeout=min(timeout, 4.0),
        require_enabled=True,
    )
    if publish_button is None:
        editor = wait_for_optional_element(
            driver,
            GLOBAL_POST_EDITOR_XPATHS,
            timeout=min(timeout, 4.0),
        ) or wait_for_element(
            dialog_provider,
            EDITOR_XPATHS,
            timeout=timeout,
            label="editor_before_publish_retry",
            debug_driver=driver,
        )
        fill_editor_with_keys(driver, editor, message)
        time.sleep(1)

    publish_button = wait_for_optional_element(
        driver,
        GLOBAL_PUBLISH_BUTTON_XPATHS,
        timeout=min(timeout, 6.0),
        require_enabled=True,
    )
    if publish_button is None:
        screenshot_path, html_path = dump_debug(driver, f"{DEBUG_OUTPUT_PREFIX}_publish_not_ready")
        note = ""
        if contains_non_bmp_characters(message):
            note = (
                " The original message includes non-BMP characters such as emoji; "
                "Facebook may require manual verification if those were stripped during fallback typing."
            )
        raise RuntimeError(
            "The post editor was filled, but the publish button did not become enabled. "
            f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
            f"{note}"
        )


def publish_post(driver: Any, *, timeout: float) -> None:
    button = wait_for_optional_element(
        driver,
        GLOBAL_PUBLISH_BUTTON_XPATHS,
        timeout=min(timeout, 6.0),
        require_enabled=True,
    )
    if button is None:
        dialog_provider = build_post_dialog_provider(driver)
        button = wait_for_element(
            dialog_provider,
            PUBLISH_BUTTON_XPATHS,
            timeout=timeout,
            label="publish_button",
            require_enabled=True,
            debug_driver=driver,
        )
    click_element(driver, button)


def create_group_post(
    group_url: str,
    cookies: list[dict[str, str]],
    *,
    message: str,
    publish: bool,
    headless: bool = False,
    timeout: float = 20.0,
    page_load_wait: float = 6.0,
    post_submit_wait: float = 8.0,
) -> None:
    driver = build_driver(headless=headless)

    try:
        login_with_cookies(driver, cookies)
        ensure_logged_in(driver)

        driver.get(group_url)
        print(f"Opened group URL: {group_url}")
        time.sleep(page_load_wait)
        close_popups(driver)

        open_group_post_composer(driver, timeout=timeout)
        fill_post_editor(
            driver,
            message,
            timeout=timeout,
            require_publish_button=publish,
        )

        if not publish:
            print("Composer opened and content inserted. Dry run complete; post was not published.")
            return

        publish_post(driver, timeout=timeout)
        time.sleep(post_submit_wait)
        print("Publish button clicked. Check the group for moderation or success state.")
    finally:
        driver.quit()


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    message = resolve_message(args.message, args.message_file)
    create_group_post(
        args.group_url,
        cookies,
        message=message,
        publish=args.publish,
        headless=args.headless,
        timeout=args.timeout,
        page_load_wait=args.page_load_wait,
        post_submit_wait=args.post_submit_wait,
    )


if __name__ == "__main__":
    main()
