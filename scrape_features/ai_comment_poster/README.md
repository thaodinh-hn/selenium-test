# AI Comment Poster

Automate Facebook comment posting with optional AI generation using OpenAI.

## Features

- Log in with Facebook cookies
- Navigate to a specific post
- Fill and submit comments automatically
- AI-powered comment generation using OpenAI
- Dry-run mode (preview before publishing)
- Detailed debug logging and screenshots on failures

## Installation

Install dependencies:
```bash
pip install openai  # For AI generation features
```

## Usage

### Basic: Post a predefined comment

```bash
.venv/bin/python scrape_features/ai_comment_poster/run.py \
  --cookie-file fb_cookie.txt \
  --post-url "https://www.facebook.com/groups/.../posts/..." \
  --comment "Your comment text here"
```

### Dry-run: Preview without publishing

```bash
.venv/bin/python scrape_features/ai_comment_poster/run.py \
  --cookie-file fb_cookie.txt \
  --post-url "https://www.facebook.com/groups/.../posts/..." \
  --comment "Your comment text"
```

(Without `--publish` flag, the comment is filled but NOT submitted)

### From file: Load comment from a text file

```bash
.venv/bin/python scrape_features/ai_comment_poster/run.py \
  --cookie-file fb_cookie.txt \
  --post-url "https://www.facebook.com/groups/.../posts/..." \
  --comment-file /path/to/comment.txt \
  --publish
```

### AI generation: Auto-generate comment with OpenAI

```bash
OPENAI_API_KEY="sk-..." \
OPENAI_MODEL="gpt-4o" \
OPENAI_PROMPT="Write a friendly comment about this post" \
.venv/bin/python scrape_features/ai_comment_poster/run.py \
  --cookie-file fb_cookie.txt \
  --post-url "https://www.facebook.com/groups/.../posts/..." \
  --use-ai \
  --publish
```

### Debug mode: See detailed editor scanning logs

```bash
.venv/bin/python scrape_features/ai_comment_poster/run.py \
  --cookie-file fb_cookie.txt \
  --post-url "https://www.facebook.com/groups/.../posts/..." \
  --comment "Test" \
  --debug-editor-scan
```

## Command-line Options

```
--cookie-file         Path to raw Facebook cookie file (default: fb_cookie.txt)
--post-url           Facebook post URL where comment will be added (required)
--comment            Inline comment content (use OR --comment-file OR --use-ai)
--comment-file       Path to UTF-8 text file with comment content
--use-ai             Generate comment via OpenAI
--publish            Actually submit the comment (dry-run if omitted)
--headless           Run Chrome in headless mode
--timeout            Max seconds to wait for UI elements (default: 20.0)
--page-load-wait     Seconds to wait after opening post page (default: 5.0)
--debug-editor-scan  Print detailed editor detection logs
--ai-model           OpenAI model (env: OPENAI_MODEL)
--ai-prompt          Prompt for AI generation (env: OPENAI_PROMPT)
```

## Environment Variables

For AI generation:
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_MODEL` - Model to use (e.g., `gpt-4o`, `gpt-3.5-turbo`)
- `OPENAI_PROMPT` - Default prompt for comment generation

## Troubleshooting

### "Could not find comment editor"

Screenshot/HTML are saved to debug folder showing what's on screen. Possible causes:
- Post URL is invalid or redirected
- Facebook UI changed - XPath patterns may need updating
- Session expired - check cookies

### Comment text not inserted correctly

Use fallback keyboard input instead of JavaScript:
- The script auto-retries with keyboard input if JS insertion fails
- Check debug screenshots in `scrape_features/ai_comment_poster/debug/`

### OpenAI errors

- Ensure `OPENAI_API_KEY` is set and valid
- Check `OPENAI_MODEL` is available in your account
- Verify `OPENAI_PROMPT` is not empty

## Output Files

Debug files saved to: `scrape_features/ai_comment_poster/debug/`
- Screenshots of failures: `manual_comment_*.png`
- HTML snapshots: `manual_comment_*.html`

