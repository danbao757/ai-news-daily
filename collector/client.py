"""OpenAI 兼容接口客户端：限速、退避重试、稳健 JSON 解析。

免费档（glm-4-flash）有速率限制：全局并发闸 + 请求最小间隔；
429/5xx 指数退避重试。所有调用走 chat_json()，返回解析后的 dict。
"""

import json
import re
import threading
import time

import requests

from . import config


class LLMError(Exception):
    pass


class _Limiter:
    """全局并发闸 + 相邻请求最小间隔（免费档防 429）。"""

    def __init__(self, concurrency: int, min_interval: float):
        self.sem = threading.Semaphore(concurrency)
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last_start = 0.0

    def __enter__(self):
        self.sem.acquire()
        with self.lock:
            wait = self.last_start + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last_start = time.time()
        return self

    def __exit__(self, *exc):
        self.sem.release()
        return False


_LIMITER = _Limiter(config.LLM_CONCURRENCY, config.LLM_MIN_INTERVAL)


def _extract_json(text: str):
    """从模型输出里稳健提取 JSON 对象（剥代码围栏；raw_decode 正确处理字符串内的花括号）。"""
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = text.find("{")
    if start == -1:
        raise LLMError(f"返回中找不到 JSON 对象: {text[:200]}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except ValueError as exc:
        raise LLMError(f"JSON 解析失败({exc}): {text[:200]}") from exc


def chat_json(system: str, user: str, model: str | None = None,
              temperature: float = 0.2, max_tokens: int = 2048) -> dict:
    """一次对话调用，要求模型只回 JSON，解析为 dict 返回。

    失败按 LLM_MAX_RETRIES 次退避重试（429/5xx/网络抖动/解析失败），
    仍失败抛 LLMError，由调用方决定降级路径。
    """
    if not config.LLM_API_KEY:
        raise LLMError("LLM_API_KEY 未配置")
    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"}
    payload = {
        "model": model or config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_exc: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES):
        with _LIMITER:
            try:
                resp = requests.post(url, headers=headers, json=payload,
                                     timeout=config.LLM_TIMEOUT)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return _extract_json(content)
            except (requests.RequestException, LLMError, ValueError, KeyError, IndexError) as exc:
                last_exc = exc
        backoff = min(5 * (2 ** attempt), 90)
        time.sleep(backoff)
    raise LLMError(f"调用失败（已重试 {config.LLM_MAX_RETRIES} 次）: {last_exc}")
