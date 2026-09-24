"""LLM 加工：中文标题、摘要、分类、标签、重要性评分。OpenAI 兼容接口。"""

import json
import re

import requests

from . import config

SYSTEM_PROMPT = "你是资深 AI 行业编辑，为一份面向中文创作者的每日 AI 日报加工稿件，只输出 JSON。"

USER_PROMPT_TMPL = """请处理以下新闻条目，输出 JSON 对象数组（除 JSON 外不要输出任何内容）。每个对象字段：
- "id": 原样返回编号
- "title_zh": 简洁有力的中文标题，不超过 28 字，不加书名号/引号
- "summary_zh": 1-2 句中文摘要（合计不超过 80 字），只陈述事实，不使用夸张措辞
- "category": 从 ["模型","产品","行业","论文","开源","政策","观点"] 中选最贴切的一个
- "tags": 最多 3 个短标签，如 "OpenAI"、"开源"、"智能体"、"视频生成"
- "score": 0-100 整数，重要性评分。锚点：90+ 行业级重大突破；75-89 头部厂商重要发布或重磅模型；60-74 有影响的更新、大额融资；40-59 常规功能更新或边际新闻；40 以下 个人观点、重复消息
- "keep": 布尔值。与 AI/AIGC 强相关且值得收录进日报为 true，否则 false

条目列表：
{items}

只输出 JSON 数组。"""

FALLBACK_CATEGORY = "未分类"


def _build_prompt(items: list[dict]) -> str:
    lines = []
    for it in items:
        lines.append(f"[{it['id']}] 来源:{it['source']} | 语言:{it['lang']} | 标题:{it['title']}")
        if it.get("summary_raw"):
            lines.append(f"      原文摘要:{it['summary_raw'][:300]}")
    return USER_PROMPT_TMPL.format(items="\n".join(lines))


def _extract_json_array(text: str):
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 返回中找不到 JSON 数组: {text[:200]}")
    return json.loads(text[start : end + 1])


def _chat(prompt: str) -> str:
    resp = requests.post(
        f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={
            "model": config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def process(items: list[dict]) -> list[dict]:
    """批量调用 LLM 加工，把结果字段合并回条目。"""
    results = []
    for i in range(0, len(items), config.LLM_BATCH_SIZE):
        batch = items[i : i + config.LLM_BATCH_SIZE]
        prompt = _build_prompt(batch)
        try:
            parsed = _extract_json_array(_chat(prompt))
        except Exception as exc:
            print(f"  [warn] LLM 批次 {i // config.LLM_BATCH_SIZE} 失败({exc})，该批降级为原始条目")
            results.extend(_fallback(batch))
            continue
        by_id = {p.get("id"): p for p in parsed if isinstance(p, dict)}
        for it in batch:
            p = by_id.get(it["id"], {})
            results.append({
                **it,
                "title_zh": str(p.get("title_zh") or it["title"])[:60],
                "summary_zh": str(p.get("summary_zh") or "")[:160],
                "category": p.get("category") if p.get("category") in
                           {"模型", "产品", "行业", "论文", "开源", "政策", "观点"} else FALLBACK_CATEGORY,
                "tags": [str(t)[:12] for t in (p.get("tags") or [])][:3],
                "score": max(0, min(100, int(p.get("score") or 50))),
                "keep": bool(p.get("keep", True)),
            })
    return results


def _fallback(items: list[dict]) -> list[dict]:
    """无 API key 或调用失败时的降级输出：原文标题 + 截断摘要。"""
    return [
        {
            **it,
            "title_zh": it["title"][:60],
            "summary_zh": (it.get("summary_raw") or "")[:120],
            "category": FALLBACK_CATEGORY,
            "tags": [],
            "score": 50,
            "keep": True,
        }
        for it in items
    ]
