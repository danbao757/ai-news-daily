"""海外源采集器：写 data/inbox/YYYY-MM-DD.jsonl（GitHub Actions 海外 runner 用）。

分工（见 HANDOFF）：Actions 定时抓海外源 + HN，原始候选落 inbox 提交进仓库；
国内服务器消费 inbox 并直抓国内源，完成 LLM 加工与聚类（pipeline.py）。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from . import config
from .sources import collect_hackernews, collect_rss
from .steps import BEIJING

ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = ROOT / "data" / "inbox"


def main() -> int:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(BEIJING).strftime("%Y-%m-%d")
    items = []
    print("== 抓取海外源 ==")
    for src in config.RSS_SOURCES:
        if src.get("region") == "overseas":
            items.extend(collect_rss(src, config.WINDOW_HOURS))
    if config.HN_ENABLED:
        items.extend(collect_hackernews(config.WINDOW_HOURS))
    items = [it for it in items if it.get("title") and it.get("url")]

    path = INBOX_DIR / f"{today}.jsonl"
    path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items) + "\n",
        encoding="utf-8")
    print(f"inbox 写入 {len(items)} 条 → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
