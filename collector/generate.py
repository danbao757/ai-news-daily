"""主流程：采集 → 去重 → LLM 加工 → 选稿 → 写入 data/issues/YYYY-MM-DD.json

用法（在项目根目录）：
    python -m collector.generate            # 生成今日日报（已存在则跳过）
    FORCE=1 python -m collector.generate    # 覆盖重新生成
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import config, llm
from .dedup import SeenStore
from .sources import collect_hackernews, collect_rss

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ISSUES_DIR = DATA_DIR / "issues"


def collect_all(window_hours: int) -> list[dict]:
    print("== 采集 ==")
    items = []
    for src in config.RSS_SOURCES:
        items.extend(collect_rss(src, window_hours))
    if config.HN_ENABLED:
        items.extend(collect_hackernews(window_hours))
    return items


def cap_per_source(items: list[dict]) -> list[dict]:
    """每个源最多保留 MAX_PER_SOURCE 条（时间倒序，最新的保留）。"""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        grouped[it["source"]].append(it)
    kept = []
    for src, lst in grouped.items():
        lst.sort(key=lambda x: x.get("published_ts") or 0, reverse=True)
        kept.extend(lst[: config.MAX_PER_SOURCE])
    return kept


def select(processed: list[dict]) -> tuple[list[dict], list[dict]]:
    kept = [it for it in processed if it.get("keep", True)]
    kept.sort(key=lambda x: (x.get("score", 0), x.get("priority", 0)), reverse=True)
    head_ids = {id(it) for it in kept[: config.MAX_HEADLINES]}
    headlines = [it for it in kept if id(it) in head_ids]
    briefing = [it for it in kept if id(it) not in head_ids][: config.MAX_BRIEFING]
    return headlines, briefing


def main() -> int:
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    issue_path = ISSUES_DIR / f"{today}.json"
    force = bool(os.environ.get("FORCE"))
    if issue_path.exists():
        if not force:
            print(f"{today} 的日报已存在，跳过（FORCE=1 可覆盖重新生成）")
            return 0
        # 覆盖重跑：沿用原期号
        try:
            issue_no = json.loads(issue_path.read_text(encoding="utf-8"))["issue"]
        except Exception:
            issue_no = len(sorted(ISSUES_DIR.glob("*.json"))) + 1
    else:
        issue_no = len(sorted(ISSUES_DIR.glob("*.json"))) + 1
    window = config.FIRST_RUN_WINDOW_HOURS if len(sorted(ISSUES_DIR.glob("*.json"))) == 0 else config.WINDOW_HOURS

    raw = collect_all(window)
    raw = [it for it in raw if it["title"] and it["url"]]
    raw = cap_per_source(raw)
    if not raw:
        print("[error] 没有采集到任何内容，请检查网络或数据源")
        return 1

    print("== 去重 ==")
    seen = SeenStore(DATA_DIR / "seen.json")
    # FORCE 重跑当日时，忽略今天记入的去重状态（相当于重建今天，但保留更早的记忆）
    ignore_after = (
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        if force
        else None
    )
    fresh = [it for it in raw if not seen.is_dup(it, ignore_after)]
    dup_count = len(raw) - len(fresh)
    print(f"  采集 {len(raw)} 条，去重 {dup_count} 条，剩余 {len(fresh)} 条")
    for it in raw:  # 本期见过的全部记入，避免下期重复
        seen.add(it)

    print("== LLM 加工 ==")
    if config.LLM_API_KEY:
        print(f"  模型: {config.LLM_MODEL} @ {config.LLM_BASE_URL}")
        processed = llm.process(fresh)
    else:
        print("  未配置 LLM_API_KEY，降级为原始条目（无翻译/摘要/评分）")
        processed = llm._fallback(fresh)

    headlines, briefing = select(processed)
    if not headlines and not briefing:
        print("[error] 选稿结果为空")
        return 1

    issue = {
        "issue": issue_no,
        "date": today,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "collected": len(raw),
            "duplicates": dup_count,
            "selected": len(headlines) + len(briefing),
            "sources": sorted({it["source"] for it in headlines + briefing}),
        },
        "headlines": [_clean(it) for it in headlines],
        "briefing": [_clean(it) for it in briefing],
    }
    issue_path.write_text(
        json.dumps(issue, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    seen.save()

    print(f"== 完成：第 {issue_no} 期 · {today} ==")
    for section, lst in (("头条", headlines), ("速览", briefing)):
        for it in lst:
            print(f"  [{it['score']:>3}] [{section}] {it['title_zh']}  ({it['source']})")
    print(f"已写入 {issue_path}")
    return 0


def _clean(it: dict) -> dict:
    """只保留前端需要的字段。"""
    return {
        "title_zh": it["title_zh"],
        "title_orig": it["title"],
        "summary_zh": it.get("summary_zh", ""),
        "category": it.get("category", llm.FALLBACK_CATEGORY),
        "tags": it.get("tags", []),
        "score": it.get("score", 0),
        "source": it["source"],
        "url": it["url"],
        "published_at": (
            datetime.fromtimestamp(it["published_ts"]).isoformat(timespec="minutes")
            if it.get("published_ts")
            else None
        ),
    }


if __name__ == "__main__":
    sys.exit(main())
