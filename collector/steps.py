"""逐条多步编辑管线（移植自 AIHOT editorial/analyze.ts）：

  1. prefilter  宽召回 AI 相关性预筛（PASS/BLOCK/UNKNOWN；UNKNOWN 视同 PASS）
  2. score      五轴加权评分 × 2 次独立调用，两次之和 ≥ 2×分级门槛才精选
  3. structure  分类/标签/主体公司/事实框架（与评分无依赖）
  4. writing    精选与近精选（平均分 > UNDERSTAND_FLOOR）用「内容理解」档
                （标题+答案先行摘要+推荐理由+标签+内容类型），其余用便宜「翻译」档
  5. 身份校验   代码层防幻觉：中文标题/摘要里的公司原文没提到 → 退回（AIHOT
                writing.ts enforceIdentity 的移植）

每条独立处理、互不影响；单步失败有降级路径，整条失败不阻塞批次。
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone

from . import config
from .client import LLMError, chat_json
from .prompts import prompt_text
from .taxonomy import (
    CATEGORY_KEY_BY_ITEM_TYPE, CATEGORY_KEYS, ENTITIES, ITEM_TYPES,
    match_entities, normalize_tags,
)

BEIJING = timezone(timedelta(hours=8))

# 标题命中即判软文/无关（预筛前的一道免费闸，省一次 LLM 调用）
_JUNK_TITLE_RE = re.compile(
    r"(招聘|诚聘|急聘|内推|hiring|"
    r"行情|股价|收盘|盘前|市值蒸发|"
    r"优惠券|促销|赞助内容|sponsored|advertorial|"
    r"付费课程|训练营)",
    re.IGNORECASE,
)

_MAX_BODY_CHARS = 6000


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def _beijing_now_iso() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _published_iso(raw: dict) -> str | None:
    ts = raw.get("published_ts")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts, BEIJING).isoformat(timespec="minutes")
    except (ValueError, OSError, OverflowError):
        return None


def _body_text(raw: dict) -> str:
    body = (raw.get("summary_raw") or "").strip() or raw.get("title", "")
    return body[:_MAX_BODY_CHARS]


def _pub_time_line(raw: dict) -> str:
    iso = _published_iso(raw)
    return iso or _beijing_now_iso()


# ── 各步骤 ──────────────────────────────────────────────────────────────────

def run_prefilter(raw: dict) -> str:
    """PASS / BLOCK / UNKNOWN。失败视为 UNKNOWN（宽召回，不误杀）。"""
    user = (f"【标题】\n{raw.get('title', '')}\n\n"
            f"【摘要】\n{_body_text(raw)}")
    try:
        data = chat_json(prompt_text("prefilter"), user, temperature=0, max_tokens=512)
        label = str(data.get("label", "")).upper()
        return label if label in ("PASS", "BLOCK", "UNKNOWN") else "UNKNOWN"
    except LLMError as exc:
        print(f"  [warn] prefilter 失败({exc})，按 UNKNOWN 继续: {raw.get('title', '')[:40]}")
        return "UNKNOWN"


def _score_input(raw: dict) -> str:
    return ("请按系统规则评估以下单篇材料所代表的事件。只输出 attentionScore。\n\n"
            f"【发布时间（北京时间）】\n{_pub_time_line(raw)}\n\n"
            f"【标题】\n{(raw.get('title') or '').strip()}\n\n"
            f"【正文】\n{_body_text(raw)}")


def run_scores(raw: dict) -> list[int] | None:
    """两次独立评分。全部成功返回 [s1, s2]；失败返回 None（不精选，继续降档写作）。"""
    values: list[int] = []
    user = _score_input(raw)
    for i in range(2):
        try:
            data = chat_json(prompt_text("score"), user, model=config.SCORE_MODEL,
                             temperature=0.2, max_tokens=1024)
            values.append(max(0, min(100, int(data["attentionScore"]))))
        except (LLMError, KeyError, TypeError, ValueError):
            return None
    return values


def run_structure(raw: dict) -> dict:
    user = (f"【来源】{raw.get('source', '')}\n"
            f"【标题】{raw.get('title', '')}\n"
            f"【摘要】{_body_text(raw)}")
    try:
        data = chat_json(prompt_text("structure"), user, temperature=0.2, max_tokens=800)
    except LLMError:
        return {}
    category = data.get("category")
    if category not in CATEGORY_KEYS:
        category = None
    subjects = [s for s in (data.get("subjects") or []) if s in ENTITIES][:6]
    fact = data.get("fact")
    if not isinstance(fact, dict):
        fact = None
    return {
        "category": category,
        "tags": normalize_tags(data.get("tags")),
        "subjects": subjects,
        "fact": {
            "title": str(fact.get("title") or "")[:60] or None,
            "subject": str(fact.get("subject") or "")[:60] or None,
            "action": str(fact.get("action") or "")[:60] or None,
            "object": str(fact.get("object") or "")[:120] or None,
            "occurred_at": fact.get("occurredAt") or None,
        } if fact else None,
    }


def run_understand(raw: dict) -> dict:
    user = (f"【来源】{raw.get('source', '')}（{'官方一手' if raw.get('first_party') else '第三方'}）\n"
            f"【语言】{raw.get('lang', 'en')}\n"
            f"【标题】{raw.get('title', '')}\n\n"
            f"【正文】\n{_body_text(raw)}")
    data = chat_json(prompt_text("understand"), user, model=config.WRITE_MODEL,
                     temperature=0.2, max_tokens=4096)
    item_type = data.get("itemType")
    if item_type not in ITEM_TYPES:
        item_type = None
    return {
        "item_type": item_type,
        "author_role": data.get("authorRole") if data.get("authorRole") in
                       ("principal", "observer", "relayer") else None,
        "tags": normalize_tags(data.get("tags")),
        "reason_zh": str(data.get("editorialJudgment") or "").strip()[:200] or None,
        "title_zh": str(data.get("titleZh") or "").strip()[:80],
        "summary_zh": str(data.get("summaryZh") or "").strip()[:600],
    }


def run_summarize(raw: dict) -> dict:
    user = (f"【来源】{raw.get('source', '')}\n"
            f"【语言】{raw.get('lang', 'en')}\n"
            f"【标题】{raw.get('title', '')}\n\n"
            f"【摘要】{_body_text(raw)}")
    data = chat_json(prompt_text("summarize"), user, model=config.WRITE_MODEL,
                     temperature=0.2, max_tokens=1024)
    return {
        "title_zh": str(data.get("titleZh") or "").strip()[:80],
        "summary_zh": str(data.get("summaryZh") or "").strip()[:400],
    }


# ── 身份校验（防张冠李戴，代码层零成本）────────────────────────────────────

def enforce_identity(raw: dict, title_zh: str, summary_zh: str) -> tuple[str, str, dict]:
    """中文标题/摘要里出现的公司，原文（原标题+原摘要）没提到 → 退回。"""
    allowed = match_entities(f"{raw.get('title', '')} {raw.get('summary_raw', '')}")
    title_hits = match_entities(title_zh) - allowed
    summary_hits = match_entities(summary_zh) - allowed
    if title_hits:
        title_zh = raw.get("title", "")  # 退回原标题（可能是英文，前端可显示原文）
    if summary_hits:
        summary_zh = ""
    guard = {
        "outcome": "fallback" if (title_hits or summary_hits) else "pass",
        "unsupported_title": sorted(title_hits),
        "unsupported_summary": sorted(summary_hits),
    }
    return title_zh, summary_zh, guard


# ── 单条全流程 ──────────────────────────────────────────────────────────────

def analyze(raw: dict) -> dict:
    """把一条原始候选加工成完整条目。BLOCK 返回 status='blocked' 的最小记录。"""
    iid = item_id(raw["url"])
    base = {
        "id": iid,
        "url": raw["url"],
        "source_id": raw.get("source_id", raw.get("source", "")),
        "source": raw["source"],
        "tier": raw.get("tier", "T2"),
        "first_party": bool(raw.get("first_party", False)),
        "lang": raw.get("lang", "en"),
        "priority": raw.get("priority", 5),
        "published_at": _published_iso(raw),
        "collected_at": _beijing_now_iso(),
        "title_orig": raw.get("title", ""),
        "summary_orig": (raw.get("summary_raw") or "")[:600],
    }

    # 免费闸：标题正则命中软文直接拦下，不花 LLM 调用
    if _JUNK_TITLE_RE.search(base["title_orig"]):
        return {**base, "status": "blocked", "prefilter": "BLOCK", "reason": "junk"}

    label = run_prefilter(raw)
    if label == "BLOCK":
        return {**base, "status": "blocked", "prefilter": "BLOCK"}

    # 评分 ×2 与结构化
    scores = run_scores(raw)
    threshold = config.threshold_of(base["tier"])
    if scores is not None:
        total = sum(scores)
        score = total // 2  # 平均分向下取整
        selected = total >= threshold * 2
    else:
        score, selected = None, False

    structure = run_structure(raw)

    # 两档写作：精选/近精选用内容理解，其余用便宜翻译档
    near = selected or (score is not None and score > config.UNDERSTAND_FLOOR)
    writer_kind = "none"
    writing: dict = {}
    if near:
        try:
            writing = run_understand(raw)
            writer_kind = "understand"
        except (LLMError, KeyError, TypeError, ValueError):
            writing = {}
    if not writing.get("title_zh"):
        try:
            writing = run_summarize(raw)
            writer_kind = "summarize"
        except (LLMError, KeyError, TypeError, ValueError):
            writing = {"title_zh": "", "summary_zh": ""}
            writer_kind = "none"
    if not writing.get("title_zh"):
        writing = {"title_zh": base["title_orig"], "summary_zh": writing.get("summary_zh", "")}
        writer_kind = "verbatim"

    title_zh, summary_zh, guard = enforce_identity(
        raw, writing.get("title_zh", ""), writing.get("summary_zh", ""))

    # 标签：内容理解档的优先（含 itemType 自洽），其次结构化档
    tags = writing.get("tags") if writer_kind == "understand" else None
    if not tags:
        tags = structure.get("tags") or []

    category = structure.get("category")
    if category is None and writing.get("item_type") in CATEGORY_KEY_BY_ITEM_TYPE:
        # 结构化失败时按内容类型兜底
        category = CATEGORY_KEY_BY_ITEM_TYPE[writing["item_type"]]

    return {
        **base,
        "status": "analyzed",
        "prefilter": label,
        "scores": scores,
        "score": score,
        "threshold": threshold,
        "selected": selected,
        "category": category,
        "item_type": writing.get("item_type") if writer_kind == "understand" else None,
        "author_role": writing.get("author_role") if writer_kind == "understand" else None,
        "tags": tags[:6],
        "subjects": structure.get("subjects", []),
        "fact": structure.get("fact"),
        "title_zh": title_zh,
        "summary_zh": summary_zh,
        "reason_zh": writing.get("reason_zh") if writer_kind == "understand" else None,
        "writer_kind": writer_kind,
        "identity_guard": guard if guard["outcome"] == "fallback" else None,
        "event_id": None,
        "event_role": None,
    }
