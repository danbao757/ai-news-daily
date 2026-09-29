"""事件聚类：把同一天里报道同一件事的多条资料聚成一个事件。

日批场景（移植自 AIHOT events/group.ts 的口径，简化为一次批量判定）：
窗口只有 1-2 天、≤百余条，不需要 embedding 召回，直接让 LLM 一次分组。
跨日续接：URL 精确命中已有事件成员（免费召回）或 LLM 判定 continue。
拿不准时宁可拆开（拆开的代价小，错合的代价大）。
"""

import hashlib

from .client import LLMError, chat_json
from .prompts import prompt_text

_MAX_CLUSTER_ITEMS = 120  # 超出时按分数截断，防止 prompt 过长


def _event_id(representative_url: str) -> str:
    return "e" + hashlib.sha1(representative_url.encode("utf-8")).hexdigest()[:10]


def _representative(members: list[dict]) -> dict:
    """代表稿：官方一手 > 已精选 > 分高 > 最新。"""
    return max(members, key=lambda m: (
        bool(m.get("first_party")), bool(m.get("selected")),
        m.get("score") or 0, m.get("published_at") or ""))


def build_events(items: list[dict], prev_events: list[dict]) -> tuple[list[dict], int]:
    """对当日 analyzed 条目聚类。

    返回 (events, grouped_count)。events 里的成员是浅拷贝（带 event_id/event_role），
    items 原列表中的对应条目也会被原地更新。prev_events 是近几天的多源事件
    （含 member_urls），用于跨日续接。失败时返回 ([], 0)，所有条目不归组。
    """
    candidates = [it for it in items if it.get("status") == "analyzed" and it.get("title_zh")]
    if len(candidates) < 2:
        return [], 0
    if len(candidates) > _MAX_CLUSTER_ITEMS:
        candidates.sort(key=lambda m: m.get("score") or 0, reverse=True)
        candidates = candidates[:_MAX_CLUSTER_ITEMS]

    # ── 免费召回：URL 精确命中已有事件成员 → 直接续接 ─────────────────────
    prev_by_url: dict[str, dict] = {}
    for ev in prev_events:
        for u in ev.get("member_urls", []):
            prev_by_url[u] = ev
    url_continued: dict[str, dict] = {}  # item id -> prev event
    for it in candidates:
        ev = prev_by_url.get(it["url"])
        if ev:
            url_continued[it["id"]] = ev

    # ── LLM 批量分组 ────────────────────────────────────────────────────────
    lines = ["今天的资料："]
    for i, it in enumerate(candidates, 1):
        score = it.get("score")
        score_s = f"{score}分" if score is not None else "未评分"
        lines.append(f"t{i}. [{it['source']}] {it['title_zh']}（{score_s}）")
    prev_list = [ev for ev in prev_events if ev.get("id") not in
                 {e.get("id") for e in url_continued.values()}]
    if prev_list:
        lines.append("\n最近几天的已有事件（id 与标题）：")
        for ev in prev_list:
            lines.append(f"{ev['id']}. {ev['title_zh']}")
    else:
        lines.append("\n最近几天没有已有事件。")
    lines.append("\n请输出分组结果。")

    by_num = {f"t{i}": it for i, it in enumerate(candidates, 1)}
    prev_ids = {ev["id"] for ev in prev_events}
    try:
        data = chat_json(prompt_text("cluster"), "\n".join(lines), temperature=0.1, max_tokens=4096)
    except (LLMError, KeyError, TypeError, ValueError) as exc:
        print(f"  [warn] 聚类调用失败({exc})，本期不归组")
        return [], 0

    groups: list[dict] = []
    seen_ids: set[str] = set()
    for g in data.get("groups") or []:
        ids = [i for i in (g.get("ids") or []) if i in by_num and i not in seen_ids]
        if len(ids) < 2:
            continue  # 单条不成事件；漏掉的条目保持未归组
        members = [by_num[i] for i in ids]
        seen_ids.update(ids)
        cont = g.get("continue_event")
        cont = cont if cont in prev_ids else None
        groups.append({"members": members, "title": str(g.get("title") or "")[:40], "continue": cont})

    # ── 组装事件（URL 命中的续接优先于 LLM 判定）───────────────────────────
    events: list[dict] = []
    for g in groups:
        members = g["members"]
        rep = _representative(members)
        cont_ev = url_continued.get(rep["id"])
        if cont_ev is None:
            for m in members:
                if m["id"] in url_continued:
                    cont_ev = url_continued[m["id"]]
                    break
        if cont_ev is None:
            cont_ev = next((ev for ev in prev_events if ev["id"] == g["continue"]), None)

        eid = cont_ev["id"] if cont_ev else _event_id(rep["url"])
        sources = sorted({m["source"] for m in members})
        events.append({
            "id": eid,
            "title_zh": g["title"] or (cont_ev["title_zh"] if cont_ev else rep["title_zh"]),
            "digest_zh": rep.get("summary_zh") or "",
            "representative_id": rep["id"],
            "member_ids": [m["id"] for m in members],
            "member_urls": [m["url"] for m in members],
            "sources": sources,
            "source_count": len(sources),
            "score_max": max((m.get("score") or 0) for m in members),
            "continued_from": cont_ev["first_seen"] if cont_ev and cont_ev.get("first_seen") != _today(members) else None,
            "first_seen": cont_ev["first_seen"] if cont_ev else _today(members),
            "latest_published_at": max((m.get("published_at") or "" for m in members), default=""),
        })
        for m in members:
            m["event_id"] = eid
            m["event_role"] = "representative" if m["id"] == rep["id"] else "member"

    grouped = sum(len(e["member_ids"]) for e in events)
    return events, grouped


def _today(members: list[dict]) -> str:
    for m in members:
        if m.get("collected_at"):
            return m["collected_at"][:10]
    return ""


def load_prev_events(events_dir, days: int, today: str) -> list[dict]:
    """读最近 N 天的事件文件（多源事件才有续接意义）。"""
    import json
    from datetime import datetime, timedelta

    out = []
    for d in range(1, days + 1):
        day = (datetime.fromisoformat(today) - timedelta(days=d)).strftime("%Y-%m-%d")
        path = events_dir / f"{day}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for ev in data.get("events", []):
            if ev.get("source_count", 0) >= 2:
                ev = dict(ev)
                ev["first_seen"] = day
                out.append(ev)
    return out[:15]
