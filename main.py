from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

FACEBOOK_BASE_URL = "https://www.facebook.com/"


def convert_raw_cookie(file_path: str | Path) -> list[dict[str, str]]:
    raw = Path(file_path).read_text(encoding="utf-8").strip()
    cookies: list[dict[str, str]] = []

    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue

        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue

        cookies.append({"name": name, "value": value})

    return cookies


def normalize_cookie_for_facebook(cookie: dict[str, str]) -> dict[str, str]:
    normalized = dict(cookie)
    normalized["name"] = (normalized.get("name") or "").strip()
    normalized["value"] = normalized.get("value") or ""
    normalized.setdefault("domain", ".facebook.com")
    normalized.setdefault("path", "/")
    return normalized


def has_active_facebook_session(driver) -> bool:
    try:
        c_user_cookie = driver.get_cookie("c_user")
    except Exception:  # pragma: no cover
        c_user_cookie = None

    return bool(c_user_cookie and (c_user_cookie.get("value") or "").strip())


def login_with_cookies(
    driver,
    cookies: list[dict[str, str]],
    *,
    base_url: str = FACEBOOK_BASE_URL,
    initial_wait: float = 2.0,
    post_login_wait: float = 3.0,
) -> None:
    driver.get(base_url)
    time.sleep(initial_wait)

    applied_cookie_names: list[str] = []
    for cookie in cookies:
        normalized_cookie = normalize_cookie_for_facebook(cookie)
        if not normalized_cookie["name"]:
            continue

        try:
            driver.add_cookie(normalized_cookie)
            applied_cookie_names.append(normalized_cookie["name"])
        except Exception as exc:  # pragma: no cover
            print(f"Skipped cookie {normalized_cookie['name']}: {exc}")

    driver.get(base_url)
    time.sleep(post_login_wait)

    if not applied_cookie_names:
        raise RuntimeError("Could not add any Facebook cookies to the browser session.")

    if not has_active_facebook_session(driver):
        raise RuntimeError(
            "Facebook login via cookie did not become active. "
            "Refresh fb_cookie.txt with a valid logged-in cookie string."
        )


def build_driver(
    headless: bool = False,
    chrome_user_data_dir: str | None = None,
    chrome_debugger_address: str | None = None,
):
    try:
        from selenium import webdriver
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "selenium is not installed. Create a venv and run: .venv/bin/pip install selenium"
        ) from exc

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    if chrome_debugger_address:
        options.debugger_address = chrome_debugger_address
    if chrome_user_data_dir:
        profile_path = Path(chrome_user_data_dir).expanduser().resolve()
        options.add_argument(f"--user-data-dir={profile_path}")
    if headless:
        options.add_argument("--headless=new")

    return webdriver.Chrome(options=options)


def bring_chrome_to_front() -> None:
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Google Chrome" to activate',
            ],
            check=False,
        )
    except Exception:  # pragma: no cover
        pass


def build_profile_url(uid: str) -> str:
    uid = uid.strip()
    if uid.isdigit():
        return f"https://www.facebook.com/profile.php?id={uid}"
    return f"https://www.facebook.com/{uid}"


def send_friend_request(
    cookies: list[dict[str, str]],
    uid: str,
    *,
    headless: bool = False,
    chrome_user_data_dir: str | None = None,
    chrome_debugger_address: str | None = None,
) -> None:
    try:
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as ec
        from selenium.webdriver.support.ui import WebDriverWait
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "selenium is not installed. Create a venv and run: .venv/bin/pip install selenium"
        ) from exc

    driver = build_driver(
        headless=headless,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_debugger_address=chrome_debugger_address,
    )

    try:
        login_with_cookies(driver, cookies)

        profile_url = build_profile_url(uid)
        driver.get(profile_url)
        print(f"Opened profile URL: {profile_url}")

        button = WebDriverWait(driver, 15).until(
            ec.element_to_be_clickable(
                (
                    By.XPATH,
                    "//div[@aria-label='Thêm bạn bè' or @aria-label='Add Friend']"
                    "|//span[normalize-space()='Thêm bạn bè' or normalize-space()='Add friend']"
                    "/ancestor::*[@role='button'][1]"
                    "|//*[@role='button' and (.//span[normalize-space()='Thêm bạn bè' or normalize-space()='Add friend'])]",
                )
            )
        )
        button.click()
        print(f"Friend request sent to UID: {uid}")
        time.sleep(5)
    except TimeoutException as exc:
        screenshot_path = Path("facebook_timeout.png").resolve()
        html_path = Path("facebook_timeout.html").resolve()
        driver.save_screenshot(str(screenshot_path))
        html_path.write_text(driver.page_source, encoding="utf-8")
        raise RuntimeError(
            "Could not find the Add Friend button. "
            f"Current URL: {driver.current_url}. "
            f"Saved screenshot to {screenshot_path} and HTML to {html_path}."
        ) from exc
    finally:
        driver.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load Facebook cookies and send a friend request to a target UID."
    )
    parser.add_argument(
        "--cookie-file",
        default="fb_cookie.txt",
        help="Path to a raw cookie string file.",
    )
    parser.add_argument("--uid", required=True, help="Facebook UID or profile slug.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode.",
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        help="Path to a Chrome user data directory to reuse an existing signed-in profile.",
    )
    parser.add_argument(
        "--chrome-debugger-address",
        help="Debugger address for an already-open Chrome instance, for example 127.0.0.1:9222.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cookies = convert_raw_cookie(args.cookie_file)
    if not cookies:
        raise SystemExit(f"No valid cookies found in {args.cookie_file}")

    send_friend_request(
        cookies,
        args.uid,
        headless=args.headless,
        chrome_user_data_dir=args.chrome_user_data_dir,
        chrome_debugger_address=args.chrome_debugger_address,
    )


if __name__ == "__main__":
    main()
