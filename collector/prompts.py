"""加载 collector/prompts/ 下的提示词。"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_cache: dict[str, str] = {}


def prompt_text(name: str) -> str:
    """读取提示词原文（带缓存）。文件名不含 .md 后缀。"""
    if name not in _cache:
        path = PROMPTS_DIR / f"{name}.md"
        _cache[name] = path.read_text(encoding="utf-8").strip()
    return _cache[name]
