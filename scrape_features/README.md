# Scrape Features

Each scraping feature now has its own folder:

- `scrape_features/group_posts/`
- `scrape_features/posts_only/`
- `scrape_features/post_bodies/`
- `scrape_features/comment_replies/`

Use each `run.py` file as the feature-specific entrypoint.

Default output/debug files are also grouped by feature:

- `scrape_features/group_posts/data/` and `scrape_features/group_posts/debug/`
- `scrape_features/posts_only/data/` and `scrape_features/posts_only/debug/`
- `scrape_features/post_bodies/data/` and `scrape_features/post_bodies/debug/`
