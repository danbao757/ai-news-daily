"""一次性迁移：旧 schema 日报（headlines/briefing 内嵌条目）→ v2 三层结构。

旧期只有 13 条精选、无全量条目、无事件——迁移后是「精选-only 日期」：
  data/issues/YYYY-MM-DD.json   → 新 schema（headline_ids/briefing_ids 引用）
  data/items/YYYY-MM-DD.jsonl   → 旧条目带默认字段落盘
事件文件不生成（旧期无聚类数据）。可重复运行（幂等）。

用法：python -m collector.migrate
"""

import json
import sys
from pathlib import Path

from . import config
from .steps import item_id
from .taxonomy import LEGACY_CATEGORY_MAP

ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = ROOT / "data" / "issues"
ITEMS_DIR = ROOT / "data" / "items"

_SRC_BY_NAME = {s["name"]: s for s in config.RSS_SOURCES}


def _migrated_item(date: str, it: dict) -> dict:
    src = _SRC_BY_NAME.get(it.get("source", ""), {})
    return {
        "id": item_id(it["url"]),
        "url": it["url"],
        "source_id": src.get("id", it.get("source", "")),
        "source": it["source"],
        "tier": src.get("tier", "T2"),
        "first_party": bool(src.get("first_party", False)),
        "lang": src.get("lang", "zh" if it.get("title_orig") and "一" <= it["title_orig"][0] <= "鿿" else "en"),
        "priority": src.get("priority", 5),
        "published_at": it.get("published_at"),
        "collected_at": f"{date}T08:00:00+08:00",
        "title_orig": it.get("title_orig") or it.get("title_zh", ""),
        "summary_orig": "",
        "prefilter": "PASS",
        "scores": None,               # 旧管线单次评分，无两次独立分
        "score": it.get("score", 50),
        "threshold": None,
        "selected": True,
        "category": LEGACY_CATEGORY_MAP.get(it.get("category")),
        "item_type": None,
        "author_role": None,
        "tags": it.get("tags", []),
        "subjects": [],
        "fact": None,
        "title_zh": it.get("title_zh", ""),
        "summary_zh": it.get("summary_zh", ""),
        "reason_zh": None,
        "writer_kind": "legacy",
        "identity_guard": None,
        "event_id": None,
        "event_role": None,
    }


def main() -> int:
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    migrated = 0
    for issue_path in sorted(ISSUES_DIR.glob("*.json")):
        data = json.loads(issue_path.read_text(encoding="utf-8"))
        if "headline_ids" in data:
            continue  # 已是新 schema
        date = data["date"]
        items = ([_migrated_item(date, it) for it in data.get("headlines", [])]
                 + [_migrated_item(date, it) for it in data.get("briefing", [])])
        by_id = {it["id"]: it for it in items}
        # 旧数据可能同 URL 重复（头条与速览不会，但稳妥起见）
        uniq = list(by_id.values())

        new_issue = {
            "issue": data["issue"],
            "date": date,
            "generated_at": data.get("generated_at"),
            "stats": {
                "collected": data.get("stats", {}).get("collected", len(uniq)),
                "duplicates": data.get("stats", {}).get("duplicates", 0),
                "analyzed": len(uniq),
                "blocked": 0,
                "selected": len(uniq),
                "events": 0,
                "sources": data.get("stats", {}).get("sources", []),
            },
            "lead": None,
            "headline_ids": [item_id(it["url"]) for it in data.get("headlines", [])],
            "briefing_ids": [item_id(it["url"]) for it in data.get("briefing", [])],
        }
        issue_path.write_text(json.dumps(new_issue, ensure_ascii=False, indent=2), encoding="utf-8")
        (ITEMS_DIR / f"{date}.jsonl").write_text(
            "\n".join(json.dumps(it, ensure_ascii=False) for it in uniq) + "\n",
            encoding="utf-8")
        migrated += 1
        print(f"  迁移 {date}: {len(uniq)} 条")
    print(f"完成，迁移 {migrated} 期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
