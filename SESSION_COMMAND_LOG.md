# Session Command Log

Tong hop cac lenh da xuat hien trong buoi chat nay de theo doi nhanh.

## 1) Lenh da thuc thi trong terminal (boi assistant)

```bash
./.venv/bin/python "scrape_features/comment_replies/run_execute.py" --help
```

```bash
git restore "main.py" "scrape_features/comment_replies/execute_plan.py" "scrape_features/comment_replies/README.md" && git status --short
```

```bash
./.venv/bin/python -m py_compile "scrape_features/comment_replies/execute_plan.py"
```

```bash
PYTHONPYCACHEPREFIX="./.pycache" ./.venv/bin/python -m py_compile "scrape_features/comment_replies/execute_plan.py"
```

```bash
PYTHONPYCACHEPREFIX="./.pycache" ./.venv/bin/python -m py_compile "scrape_features/comment_replies/execute_plan.py" && ./.venv/bin/python "scrape_features/comment_replies/run_execute.py" --help
```

```bash
./.venv/bin/python -m pytest "tests/scrape_features/test_comment_replies.py" -q
```

## 2) Lenh user da chay va bao loi

```bash
.venv/bin/python fb_group_poster_comment.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/ptetalents/posts/2021853212067473/" \
  --message $'Chuc ban thi that tot nhe\nDung cang qua, cu lam quen format la ok roi\nThi xong nho len update ket qua nha'
```

## 3) Lenh da de xuat trong buoi chat (tham khao)

### Comment replies (dry-run)
```bash
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless
```

### Comment replies (publish)
```bash
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --headless \
  --publish
```

### Debug editor detect (1 row)
```bash
.venv/bin/python scrape_features/comment_replies/run_execute.py \
  --cookie-file fb_cookie.txt \
  --plan-file scrape_features/comment_replies/data/comment_plan.csv \
  --result-file scrape_features/comment_replies/data/comment_results.csv \
  --only-pending \
  --limit 1 \
  --debug-editor
```

### Chay test file comment replies
```bash
.venv/bin/python -m pytest tests/scrape_features/test_comment_replies.py -q
```

### Cai pytest
```bash
.venv/bin/pip install pytest
```

### Group post composer (dang bai trong group, khong phai comment vao post)
```bash
.venv/bin/python fb_group_poster_comment.py \
  --cookie-file fb_cookie.txt \
  --group-url "https://www.facebook.com/groups/ptetalents/" \
  --message $'Chuc ban thi that tot nhe\nDung cang qua, cu lam quen format la ok roi\nThi xong nho len update ket qua nha'
```
