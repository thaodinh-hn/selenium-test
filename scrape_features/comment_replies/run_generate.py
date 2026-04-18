from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scrape_features.comment_replies.generate_plan import main


if __name__ == "__main__":
    main()
