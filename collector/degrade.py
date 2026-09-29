"""无 LLM key 时的降级加工：Google 免费接口机翻标题/摘要。

必须用 client=dict-chrome-ex（gtx 客户端会被反爬拦截返回 Sorry 页）。
中文源自动跳过翻译；失败回退原文。分类缺失、评分统一 50、不参与精选排序
（按信源 priority 与时间选稿），保证断 key 时日报仍能出刊。
"""

import time

import requests

from . import config
from .steps import _beijing_now_iso, _published_iso, item_id


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return cjk / max(len(text.replace(" ", "")), 1)


def _truncate(text: str, limit: int) -> str:
    """词边界截断：英文不拦腰截断单词，中文按字符，超长补省略号。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for i in range(len(cut) - 1, max(len(cut) - 24, 0), -1):
        if cut[i].isspace():
            return cut[:i].rstrip(" ,;:-–—") + "…"
    return cut + "…"


def _mt_zh(text: str, sess: requests.Session) -> str:
    if not text or _cjk_ratio(text) >= 0.3:
        return text
    try:
        resp = sess.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "dict-chrome-ex", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text[:1500]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        out = "".join(seg[0] for seg in data[0] if seg and seg[0])
        return out or text
    except Exception:
        return text


def degraded_items(raw_items: list[dict]) -> list[dict]:
    """机翻降级：产出 schema 与 analyze() 对齐的最小条目。"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 ai-news-daily/0.2"})
    out = []
    for raw in raw_items:
        title_zh = raw.get("title", "")
        summary_zh = (raw.get("summary_raw") or "").strip()
        if config.MT_FALLBACK_ENABLED:
            title_zh = _mt_zh(title_zh, sess)
            if summary_zh:
                summary_zh = _mt_zh(_truncate(summary_zh, 160), sess)
            time.sleep(0.15)
        out.append({
            "id": item_id(raw["url"]),
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
            "status": "analyzed",
            "prefilter": "UNKNOWN",
            "scores": None,
            "score": 50,
            "threshold": None,
            "selected": True,  # 降级模式按 priority 选稿，这里先全 True
            "category": None,
            "item_type": None,
            "author_role": None,
            "tags": [],
            "subjects": [],
            "fact": None,
            "title_zh": _truncate(title_zh, 60),
            "summary_zh": _truncate(summary_zh, 120),
            "reason_zh": None,
            "writer_kind": "mt",
            "identity_guard": None,
            "event_id": None,
            "event_role": None,
        })
    return out
