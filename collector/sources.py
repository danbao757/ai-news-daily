"""采集器：RSS 订阅 + Hacker News。统一输出 dict 列表。"""

import html
import re
import time

import feedparser
import requests

from . import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ai-news-daily/0.1"
}


def _http_get(url: str, timeout: int = 20) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _entry_timestamp(entry) -> float | None:
    for field in ("published_parsed", "updated_parsed"):
        st = getattr(entry, field, None)
        if st:
            return time.mktime(st)
    return None


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def collect_rss(source: dict, window_hours: int) -> list[dict]:
    """抓单个 RSS 源，返回时间窗口内的条目。失败只告警不中断。"""
    try:
        payload = _http_get(source["url"])
    except Exception as exc:
        print(f"  [warn] {source['name']}: 抓取失败 - {exc}")
        return []

    feed = feedparser.parse(payload)
    cutoff = time.time() - window_hours * 3600
    items = []
    for entry in feed.entries[:30]:
        ts = _entry_timestamp(entry)
        if ts and ts < cutoff:
            continue
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        items.append({
            "source": source["name"],
            "lang": source["lang"],
            "priority": source["priority"],
            "title": _strip_html(title),
            "url": url,
            "summary_raw": _strip_html(getattr(entry, "summary", "") or "")[:600],
            "published_ts": ts,
        })
    print(f"  {source['name']}: {len(items)} 条")
    return items


def collect_hackernews(window_hours: int) -> list[dict]:
    """按多组关键词查询 Algolia，按 objectID 合并去重。"""
    since = int(time.time() - window_hours * 3600)
    hits: dict[str, dict] = {}
    for q in config.HN_QUERIES:
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={q}&tags=story&hitsPerPage=20"
            f"&numericFilters=created_at_i>{since},points>{config.HN_MIN_POINTS}"
        )
        try:
            data = requests.get(url, headers=HEADERS, timeout=20).json()
        except Exception as exc:
            print(f"  [warn] HN[{q}]: 查询失败 - {exc}")
            continue
        for hit in data.get("hits", []):
            oid = hit.get("objectID")
            if oid and oid not in hits:
                hits[oid] = hit
        time.sleep(0.3)

    items = []
    for hit in hits.values():
        title = (hit.get("title") or "").strip()
        hn_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append({
            "source": "Hacker News",
            "lang": "en",
            "priority": 6,
            "title": title,
            "url": hn_url,
            "summary_raw": _strip_html(f"Hacker News 热帖，{hit.get('points', 0)} 赞 / {hit.get('num_comments', 0)} 评论。{hit.get('story_text') or ''}")[:600],
            "published_ts": hit.get("created_at_i"),
        })
    print(f"  Hacker News: {len(items)} 条")
    return items
