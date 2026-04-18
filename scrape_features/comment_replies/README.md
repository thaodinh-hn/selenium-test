# Comment Replies Automation

This feature has 2 steps:

1. Generate comment ideas from scraped posts CSV.
2. Execute comments from that plan file (dry-run first, then publish).

Execution targets the **main post comment box** (not reply thread inputs).

## 1) Generate Comment Plan

```bash
.venv/bin/python scrape_features/comment_replies/run_generate.py \
  --input scrape_features/post_bodies/data/group_post_bodies.csv \
  --output scrape_features/comment_replies/data/comment_plan.csv \
  --overwrite
```

## 2) Dry-Run Comment Execution

```bash
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless
```

## 3) Publish Real Comments

```bash
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless \
  --publish
```

Notes:
- Review the generated comments before running with `--publish`.
- The result CSV tracks per-row status:
  - `pending`
  - `dry_run_ready`
  - `commented`
  - `redirected_or_unavailable_post`
  - `comment_editor_not_found`
  - `submit_failed`
  - `failed_unexpected`
