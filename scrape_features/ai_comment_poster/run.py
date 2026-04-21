#!/usr/bin/env python3
"""
Entry point for AI Comment Poster feature.

Usage:
    python scrape_features/ai_comment_poster/run.py --cookie-file fb_cookie.txt --post-url "https://..." --comment "text"
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import convert_raw_cookie
from scrape_features.ai_comment_poster.scraper import (
    AI_SUFFIX,
    CommentBotError,
    comment_on_post,
    clean_text_content,
)


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
    else:
        raise ValueError("Either comment or comment_file must be provided.")

    normalized = content.replace("\r\n", "\n").strip()
    if not clean_text_content(normalized):
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
    except ImportError as exc:
        raise RuntimeError(
            "openai package is not installed. Install it before using --use-ai."
        ) from exc

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": final_prompt}
        ],
    )
    comment = clean_text_content((response.choices[0].message.content or "").strip())
    if not comment:
        raise RuntimeError("OpenAI returned an empty comment.")
    return comment


def resolve_runtime_comment(args: argparse.Namespace) -> str:
    if args.use_ai:
        return generate_ai_comment(args.ai_prompt, args.ai_model)
    return resolve_comment_text(args.comment, args.comment_file)


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
    print(f"\n✓ Comment status: {status}")
    if status == "dry-run":
        print("ℹ️  Editor was filled successfully. Re-run with --publish to submit the comment.")


if __name__ == "__main__":
    main()

