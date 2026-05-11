# Test Commands

## Prerequisites

- Ensure `fb_cookie.txt` contains a valid logged-in Facebook cookie string.
- Run commands from project root: `selenium-test/`.
- Prefer `.venv/bin/python` to ensure Selenium dependencies are available.

## 1) Group Posts Scraper

```bash
.venv/bin/python scrape_features/group_posts/run.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/1250416722544463/" \
  --max-posts 20 \
  --max-scrolls 10 \
  --headless
```

## 2) Posts-Only Scraper

```bash
.venv/bin/python scrape_features/posts_only/run.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/1250416722544463/" \
  --max-posts 20 \
  --max-scrolls 10 \
  --headless
```

## 3) Post-Bodies Scraper

```bash
.venv/bin/python scrape_features/post_bodies/run.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/1250416722544463/" \
  --max-posts 20 \
  --max-scrolls 10 \
  --headless
```

## 4) Group Poster (Dry Run, No Publish)

```bash
.venv/bin/python fb_group_poster.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/1250416722544463/" \
  --message "Test post from script"
```

## 5) Group Poster (Real Publish)

```bash
.venv/bin/python fb_group_poster.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/1250416722544463/" \
  --message "Test post from script" \
  --publish
```

## 6) Run Unit Tests

```bash
.venv/bin/python -m unittest \
  tests/scrape_features/test_group_posts.py \
  tests/scrape_features/test_posts_only.py \
  tests/scrape_features/test_post_bodies.py \
  tests/scrape_features/test_comment_replies.py \
  tests/test_fb_group_poster.py \
  tests/test_main.py
```

## 7) Comment Idea + Auto Reply Flow

The executor targets the main post comment box (`Viết bình luận...`) for each `post_url` in CSV.

```bash
# Step A: Generate comment plan from post bodies CSV
.venv/bin/python scrape_features/comment_replies/run_generate.py \
  --input scrape_features/post_bodies/data/group_post_bodies.csv \
  --output scrape_features/comment_replies/data/comment_plan.csv \
  --overwrite
```

```bash
# Step B: Dry-run execution (no publish)
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless
```

```bash
# Step C: Publish real comments
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless \
  --publish
```

Result status values in `comment_results.csv`:
- `pending`, `dry_run_ready`, `commented`
- `redirected_or_unavailable_post`
- `comment_editor_not_found`
- `submit_failed`
- `failed_unexpected`

## Optional: Show CLI Help

```bash
.venv/bin/python scrape_features/group_posts/run.py --help
.venv/bin/python scrape_features/posts_only/run.py --help
.venv/bin/python scrape_features/post_bodies/run.py --help
.venv/bin/python scrape_features/comment_replies/run_generate.py --help
.venv/bin/python scrape_features/comment_replies/run_execute.py --help
.venv/bin/python fb_group_poster.py --help
```

## 8) Manual Comment Bot with Visible Chrome

Use this flow when you want to watch the browser while the bot opens Facebook, navigates to a post, and types a comment visibly.

### Prepare Python Environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Close Chrome Profile `acc1`

```bash
pkill -f 'chrome-profiles-pte/acc1'
```

### Open Chrome with Remote Debugging

```bash
open -na "Google Chrome" --args --user-data-dir="$HOME/chrome-profiles-pte/acc1" --remote-debugging-port=9223 --no-first-run --no-default-browser-check
```

### Bring Chrome to the Front

```bash
osascript -e 'tell application "Google Chrome" to activate'
```

### Verify Debug Port

```bash
curl http://127.0.0.1:9223/json/version
```

### Dry Run Comment on a Specific Post

```bash
.venv/bin/python main-ai-bot-comment.py \
  --post-url 'https://www.facebook.com/groups/ptetalents/permalink/2035503874035740/' \
  --comment 'Có vẻ voucher đăng ký thi ạ' \
  --chrome-debugger-address 127.0.0.1:9223 \
  --debug-editor-scan \
  --timeout 30 \
  --page-load-wait 8
```

### Publish the Comment for Real

```bash
.venv/bin/python main-ai-bot-comment.py \
  --post-url 'https://www.facebook.com/groups/ptetalents/permalink/2035503874035740/' \
  --comment 'Có vẻ voucher đăng ký thi ạ' \
  --chrome-debugger-address 127.0.0.1:9223 \
  --debug-editor-scan \
  --timeout 30 \
  --page-load-wait 8 \
  --publish
```

### Another Example Comment

```bash
.venv/bin/python main-ai-bot-comment.py \
  --post-url 'https://www.facebook.com/groups/ptetalents/posts/2021853212067473/' \
  --comment 'Lời khuyên là ngủ đủ, giữ bình tĩnh và đừng cố học nhồi quá nhiều trước ngày thi. Speaking thì nói rõ, đều, hạn chế ngập ngừng; các phần còn lại nhớ canh thời gian, câu khó quá thì đi tiếp. Chuẩn bị giấy tờ và đến sớm một chút nha. Chúc bạn thi tốt!' \
  --chrome-debugger-address 127.0.0.1:9223 \
  --debug-editor-scan \
  --timeout 30 \
  --page-load-wait 8
```

### Alternative: Launch a Fresh Selenium Chrome Session with the Same Profile

This mode does not require remote debugging, but it may be less visible if Chrome opens in the background.

```bash
.venv/bin/python main-ai-bot-comment.py \
  --post-url 'https://www.facebook.com/groups/ptetalents/permalink/2035503874035740/' \
  --comment 'Có vẻ voucher đăng ký thi ạ' \
  --chrome-user-data-dir "$HOME/chrome-profiles-pte/acc1" \
  --debug-editor-scan \
  --timeout 30 \
  --page-load-wait 8
```

### Notes

- Do not use `--headless` if you want to watch the browser.
- Prefer `--chrome-debugger-address 127.0.0.1:9223` for visible runs.
- Keep only one Chrome window and as few Facebook tabs as possible when debugging.
- Add `--publish` only when you want to submit the comment for real.
