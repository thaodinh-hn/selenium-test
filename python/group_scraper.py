import sys

from scrape_features.group_posts import scraper as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    _impl.main()
