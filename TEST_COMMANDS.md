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
