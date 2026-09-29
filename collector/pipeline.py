"""主流程（v2 多步管线）：

    采集（inbox + 国内直抓 / 无 inbox 全量直抓）
      → 去重（14 天记忆，FORCE 忽略当日）
      → 逐条多步加工（预筛 → 五轴评分×2 → 结构化 → 两档写作，断点续跑）
      → LLM 批量聚类 → 事件（跨日续接）
      → 选稿（事件去重后取头条 3 + 速览 10）+ 日报导语
      → 落盘 data/{issues,items,events}/YYYY-MM-DD.*

用法（在项目根目录）：
    python -m collector.pipeline             # 生成今日（已存在则跳过）
    FORCE=1 python -m collector.pipeline     # 覆盖重跑当日（沿用原期号）
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import config
from .cluster import build_events, load_prev_events
from .client import LLMError, chat_json
from .dedup import SeenStore
from .degrade import degraded_items
from .prompts import prompt_text
from .sources import collect_hackernews, collect_rss
from .steps import analyze
from .taxonomy import CATEGORY_LABELS

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ISSUES_DIR = DATA_DIR / "issues"
ITEMS_DIR = DATA_DIR / "items"
EVENTS_DIR = DATA_DIR / "events"
INBOX_DIR = DATA_DIR / "inbox"
STATE_DIR = DATA_DIR / "state"

_write_lock = threading.Lock()


def _today() -> str:
    # 按北京日期出刊（Actions 海外 runner 是 UTC，不能直接用本地日期）
    from .steps import BEIJING
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


# ── 采集 ────────────────────────────────────────────────────────────────────

def _read_inbox(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return items


def collect(today: str) -> tuple[list[dict], bool]:
    """inbox（Actions 抓的海外候选）+ 本机直抓国内源。无 inbox 时全量直抓。"""
    inbox_path = INBOX_DIR / f"{today}.jsonl"
    items: list[dict] = []
    used_inbox = False
    if inbox_path.exists():
        items = _read_inbox(inbox_path)
        used_inbox = True
        print(f"== 采集 ==\n  inbox（Actions 抓取）: {len(items)} 条")

    window = config.WINDOW_HOURS
    if not used_inbox:
        print("== 采集 ==（无 inbox，全量直抓）")
        for src in config.RSS_SOURCES:
            items.extend(collect_rss(src, window))
        if config.HN_ENABLED:
            items.extend(collect_hackernews(window))
    else:
        # inbox 只有海外源；国内源本机直抓
        for src in config.RSS_SOURCES:
            if src.get("region") == "domestic":
                items.extend(collect_rss(src, window))

    items = [it for it in items if it.get("title") and it.get("url")]
    # 每源限量（时间倒序保留最新）
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        grouped[it["source"]].append(it)
    capped = []
    for lst in grouped.values():
        lst.sort(key=lambda x: x.get("published_ts") or 0, reverse=True)
        capped.extend(lst[: config.MAX_PER_SOURCE])
    return capped, used_inbox


def cap_per_source(items):  # 兼容旧名（采集时已在 collect 内限量）
    return items


# ── 断点续跑 ────────────────────────────────────────────────────────────────

def _partial_path(today: str) -> Path:
    return STATE_DIR / f"{today}.partial.jsonl"


def _load_partial(today: str) -> dict[str, dict]:
    path = _partial_path(today)
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    done[rec["url"]] = rec
                except (ValueError, KeyError):
                    continue
    return done


def _append_partial(today: str, item: dict) -> None:
    with _write_lock:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with _partial_path(today).open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ── 选稿 ────────────────────────────────────────────────────────────────────

def select_items(items: list[dict]) -> list[dict]:
    """头条 3 + 速览 10：精选优先（按 score/priority 降序），不足时按分回填近精选；
    同一事件只取最佳一条（速览不与头条重复报道）。"""
    want = config.MAX_HEADLINES + config.MAX_BRIEFING
    key = lambda x: (bool(x.get("selected")), x.get("score") or 0, x.get("priority") or 0)  # noqa: E731
    pool = sorted(items, key=key, reverse=True)
    picked, seen_events = [], set()
    # 先选精选条目做头条（事件去重）
    for it in pool:
        if not it.get("selected"):
            break
        eid = it.get("event_id")
        if eid:
            if eid in seen_events:
                continue
            seen_events.add(eid)
        picked.append(it)
    # 速览回填：近精选按分数补足（事件去重仍生效）
    for it in pool:
        if len(picked) >= want:
            break
        if it in picked:
            continue
        eid = it.get("event_id")
        if eid and eid in seen_events:
            continue
        if eid:
            seen_events.add(eid)
        picked.append(it)
    return picked[:want]


def write_lead(picked: list[dict]) -> dict | None:
    """日报导语：标题、总括段、今日看点（引用条目 id）。"""
    if not config.LLM_API_KEY or not picked:
        return None
    lines = []
    for it in picked:
        cat = CATEGORY_LABELS.get(it.get("category"), "")
        lines.append(f"{it['id']}. [{it['source']}|{cat}] {it['title_zh']}")
    try:
        data = chat_json(prompt_text("daily_lead"),
                         "今日入选条目：\n" + "\n".join(lines),
                         temperature=0.3, max_tokens=1024)
    except (LLMError, KeyError, TypeError, ValueError):
        return None
    valid_ids = {it["id"] for it in picked}
    highlights = [h for h in (data.get("highlights") or []) if h in valid_ids][:5]
    return {
        "title": str(data.get("title") or "")[:40] or None,
        "paragraph": str(data.get("leadParagraph") or "")[:200] or None,
        "highlights": highlights,
    }


# ── 主流程 ──────────────────────────────────────────────────────────────────

def main() -> int:
    for d in (ISSUES_DIR, ITEMS_DIR, EVENTS_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    today = _today()
    issue_path = ISSUES_DIR / f"{today}.json"
    force = bool(os.environ.get("FORCE"))

    if issue_path.exists() and not force:
        print(f"{today} 的日报已存在，跳过（FORCE=1 可覆盖重新生成）")
        return 0
    issue_no = _issue_no(issue_path, today, force)

    raw, used_inbox = collect(today)
    if not raw:
        print("[error] 没有采集到任何内容，请检查网络或数据源")
        return 1

    # ── 去重 ──
    print("== 去重 ==")
    seen = SeenStore(DATA_DIR / "seen.json")
    ignore_after = (
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        if force else None
    )
    fresh = [it for it in raw if not seen.is_dup(it, ignore_after)]
    dup_count = len(raw) - len(fresh)
    print(f"  采集 {len(raw)} 条，去重 {dup_count} 条，剩余 {len(fresh)} 条")
    for it in raw:
        seen.add(it)

    # ── 逐条多步加工（断点续跑：partial 里已完成的 url 直接复用）──
    analyzed: list[dict] = []
    blocked = 0
    if not config.LLM_API_KEY:
        print("== 降级模式：未配置 LLM_API_KEY，机翻标题/摘要，无评分/聚类 ==")
        items = degraded_items(fresh)
        analyzed = items
    else:
        done = {} if force else _load_partial(today)
        todo = [it for it in fresh if it["url"] not in done]
        analyzed = [done[it["url"]] for it in fresh if it["url"] in done]
        resumed = len(analyzed)
        if resumed:
            print(f"== LLM 加工 ==（断点续跑：复用已完成 {resumed} 条）")
        else:
            print(f"== LLM 加工 ==\n  模型: {config.LLM_MODEL} @ {config.LLM_BASE_URL}"
                  f"（评分 {config.SCORE_MODEL} / 写作 {config.WRITE_MODEL}，"
                  f"并发 {config.LLM_CONCURRENCY}）")
        for rec in list(analyzed):
            if rec.get("status") == "blocked":
                blocked += 1

        def _work(raw_it: dict) -> dict:
            item = analyze(raw_it)
            if item.get("status") != "blocked":
                _append_partial(today, item)
            return item

        with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as pool:
            futures = {pool.submit(_work, it): it for it in todo}
            for fut in as_completed(futures):
                try:
                    item = fut.result()
                except Exception as exc:  # 单条崩溃不阻塞批次
                    it = futures[fut]
                    print(f"  [warn] 条目处理失败({exc}): {it.get('title', '')[:40]}")
                    continue
                if item.get("status") == "blocked":
                    blocked += 1
                else:
                    analyzed.append(item)
                done_n = len(analyzed) + blocked
                if done_n % 10 == 0:
                    print(f"  进度 {done_n}/{len(fresh)}")

    live = [it for it in analyzed if it.get("status") == "analyzed"]
    if not live:
        print("[error] 没有可用条目")
        return 1

    # ── 聚类 ──
    print("== 事件聚类 ==")
    prev_events = load_prev_events(EVENTS_DIR, config.CLUSTER_LOOKBACK_DAYS, today)
    events, grouped = build_events(live, prev_events)
    multi = [e for e in events if e["source_count"] >= config.EVENT_PAGE_MIN_SOURCES]
    print(f"  事件 {len(events)} 个（多源 {len(multi)} 个），归组条目 {grouped} 条")

    # ── 选稿 ──
    picked = select_items(live)
    if not picked:
        print("[error] 选稿结果为空")
        return 1
    headlines = picked[: config.MAX_HEADLINES]
    briefing = picked[config.MAX_HEADLINES:]
    lead = write_lead(picked)

    # ── 落盘 ──
    selected_count = sum(1 for it in live if it.get("selected"))
    issue = {
        "issue": issue_no,
        "date": today,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "collected": len(raw),
            "duplicates": dup_count,
            "analyzed": len(live),
            "blocked": blocked,
            "selected": selected_count,
            "events": len(multi),
            "sources": sorted({it["source"] for it in picked}),
        },
        "lead": lead,
        "headline_ids": [it["id"] for it in headlines],
        "briefing_ids": [it["id"] for it in briefing],
    }
    issue_path.write_text(json.dumps(issue, ensure_ascii=False, indent=2), encoding="utf-8")

    def _public_item(it: dict) -> dict:
        return {k: v for k, v in it.items() if k != "status"}

    (ITEMS_DIR / f"{today}.jsonl").write_text(
        "\n".join(json.dumps(_public_item(it), ensure_ascii=False) for it in live) + "\n",
        encoding="utf-8")
    # member_urls 必须落盘：跨日续接的 URL 精确命中依赖它
    (EVENTS_DIR / f"{today}.json").write_text(
        json.dumps({"date": today, "generated_at": issue["generated_at"],
                    "events": events}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    seen.save()

    # 清理：inbox 已消费、partial 已固化
    inbox_path = INBOX_DIR / f"{today}.jsonl"
    if used_inbox and inbox_path.exists():
        inbox_path.unlink()
    partial = _partial_path(today)
    if partial.exists():
        partial.unlink()

    print(f"== 完成：第 {issue_no} 期 · {today} ==")
    for section, lst in (("头条", headlines), ("速览", briefing)):
        for it in lst:
            print(f"  [{it.get('score') or 0:>3}] [{section}] {it['title_zh']}  ({it['source']})")
    print(f"已写入 {issue_path} / items / events")
    return 0


def _issue_no(issue_path: Path, today: str, force: bool) -> int:
    """新日期期号 = 现有文件数 + 1；FORCE 重跑沿用原期号。"""
    existing = sorted(ISSUES_DIR.glob("*.json"))
    if force and issue_path.exists():
        try:
            return json.loads(issue_path.read_text(encoding="utf-8"))["issue"]
        except (ValueError, KeyError):
            pass
    return len(existing) + 1


if __name__ == "__main__":
    sys.exit(main())
