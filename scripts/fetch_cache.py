"""预取评论缓存脚本。

用法:  python -m scripts.fetch_cache [app_id]
默认:  839285684 (Workout for Women)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.tools.collector import fetch_reviews, save_cache


def main():
    app_id = sys.argv[1] if len(sys.argv) > 1 else "839285684"
    print(f"fetching reviews for app_id={app_id} ...")
    reviews = fetch_reviews(app_id)
    path = save_cache(app_id, reviews)
    print(f"cached {len(reviews)} reviews -> {path}")


if __name__ == "__main__":
    main()
