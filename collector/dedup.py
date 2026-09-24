"""去重：URL 精确匹配 + 标题字符 3-gram 相似度（中英文通用）。"""

import json
import re
import time
from pathlib import Path


def _ngrams(title: str) -> set[str]:
    """标题归一化为字符 3-gram 集合。中文按字、英文按去空格后的字母流。"""
    t = re.sub(r"[^\w一-鿿]+", "", (title or "").lower())
    if len(t) < 3:
        return {t} if t else set()
    return {t[i : i + 3] for i in range(len(t) - 2)}


def _similar(a: set[str], b: set[str], threshold: float = 0.55) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    return inter / len(a | b) >= threshold


class SeenStore:
    """跨期去重状态，落在 data/seen.json。"""

    def __init__(self, path: Path):
        self.path = path
        self.urls: dict[str, float] = {}
        self.titles: list[dict] = []  # [{"grams": [...], "ts": epoch}]
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.urls = data.get("urls", {})
                self.titles = data.get("titles", [])
            except Exception:
                pass

    def is_dup(self, item: dict, ignore_after: float | None = None) -> bool:
        """ignore_after: 忽略该时间之后记录的条目（FORCE 重跑当日时传今天 0 点）"""
        ts = self.urls.get(item["url"])
        if ts is not None and (ignore_after is None or ts < ignore_after):
            return True
        grams = _ngrams(item["title"])
        for rec in self.titles:
            if ignore_after is not None and rec["ts"] >= ignore_after:
                continue
            if _similar(grams, set(rec["grams"])):
                return True
        return False

    def add(self, item: dict) -> None:
        now = time.time()
        self.urls[item["url"]] = now
        grams = _ngrams(item["title"])
        if grams:
            self.titles.append({"grams": sorted(grams), "ts": now})

    def save(self) -> None:
        cutoff = time.time() - 14 * 86400
        self.urls = {u: ts for u, ts in self.urls.items() if ts >= cutoff}
        self.titles = [r for r in self.titles if r["ts"] >= cutoff]
        self.path.write_text(
            json.dumps({"urls": self.urls, "titles": self.titles}, ensure_ascii=False),
            encoding="utf-8",
        )
