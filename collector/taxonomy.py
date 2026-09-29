"""分类体系：类别、三层标签词表、主体名录、身份词典。

移植自 AIHOT industry/taxonomy.ts，按本项目 7 分类裁剪。
模型按这里的词表打标签；防幻觉身份词典在 steps.py 代码层强制执行
（中文标题/摘要里出现的公司，原文没提到就退回，防止张冠李戴）。
"""

import re

# ── 类别 ────────────────────────────────────────────────────────────────────
# key 出现在网址（/all?category=…）与数据文件里，上线后不要改。
# label 是界面显示名；guide 告诉模型怎么归类。

CATEGORIES = [
    {"key": "ai-models",  "label": "模型", "guide": "新模型、模型版本、权重开放、模型能力与价格变化的发布与评测结果"},
    {"key": "ai-products","label": "产品", "guide": "AI 产品、功能、应用、工具、API 与平台的发布和更新"},
    {"key": "industry",   "label": "行业", "guide": "公司经营、融资并购、人事、合作、诉讼、监管与政策、市场与基础设施"},
    {"key": "paper",      "label": "论文", "guide": "研究论文、技术报告、基准与数据集"},
    {"key": "open-source","label": "开源", "guide": "开源项目、仓库发布与重要更新、开源生态动态"},
    {"key": "policy",     "label": "政策", "guide": "政府监管、立法、标准、安全与合规政策"},
    {"key": "opinion",    "label": "观点", "guide": "人物观点、评论、分析、访谈、现象与趋势讨论"},
]

CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
CATEGORY_LABELS = {c["key"]: c["label"] for c in CATEGORIES}
CATEGORY_GUIDE = "\n".join(f"- {c['key']}（{c['label']}）：{c['guide']}" for c in CATEGORIES)

# 旧 schema 的中文分类名 → 新 key（迁移脚本与降级路径用）
LEGACY_CATEGORY_MAP = {
    "模型": "ai-models", "产品": "ai-products", "行业": "industry", "论文": "paper",
    "开源": "open-source", "政策": "policy", "观点": "opinion", "未分类": None,
}

# ── 内容类型（评分提示词按类型套权重表）────────────────────────────────────

ITEM_TYPES = [
    "model_release", "product_launch", "tool_or_prompt", "research_paper",
    "industry_event", "opinion_analysis", "tutorial_explainer",
]

# ── 标签词表 ────────────────────────────────────────────────────────────────

# 每条目的第一个标签必须是这些分类标签之一
CATEGORY_TAGS = [
    "模型发布", "产品更新", "论文/研究", "开源/仓库", "教程/实践", "现象/趋势",
    "大佬观点", "评测/基准", "安全/对齐", "行业动态", "政策/监管",
    "非AI/通用工具", "其他",
]

# 可选主题标签
TOPIC_TAGS = [
    "Agent", "编码", "推理", "多模态", "语音", "视频", "图像生成", "RAG", "端侧",
    "数据/训练", "搜索", "部署/工程", "开源生态", "具身智能", "MCP/工具调用",
]

# 可选实体标签（显示用）
ENTITY_TAGS = ["OpenAI", "Anthropic", "DeepSeek", "DeepMind", "Google", "Meta",
               "Microsoft", "xAI", "Hugging Face", "GitHub", "arXiv"]

# 模型常写的近义词 → 词表写法
TAG_SYNONYMS = {
    "教程/玩法": "教程/实践", "技巧/最佳实践": "教程/实践", "合作/生态": "行业动态",
    "融资/收购": "行业动态", "公司动态": "行业动态", "合作": "行业动态", "生态": "行业动态",
    "融资": "行业动态", "收购": "行业动态", "投资": "行业动态", "并购": "行业动态",
    "政策": "政策/监管", "监管": "政策/监管", "法规": "政策/监管",
    "安全": "安全/对齐", "对齐": "安全/对齐",
    "论文": "论文/研究", "研究": "论文/研究", "paper": "论文/研究", "papers": "论文/研究",
    "open-source": "开源/仓库", "开源": "开源/仓库", "仓库": "开源/仓库", "repo": "开源/仓库",
    "教程": "教程/实践", "玩法": "教程/实践", "指南": "教程/实践", "技巧": "教程/实践",
    "最佳实践": "教程/实践", "实践": "教程/实践",
    "产品": "产品更新", "更新": "产品更新", "发布": "模型发布", "模型": "模型发布",
    "趋势": "现象/趋势", "现象": "现象/趋势", "观点": "大佬观点",
    "视频生成": "视频", "非ai": "非AI/通用工具", "non-ai": "非AI/通用工具",
    "通用工具": "非AI/通用工具", "工程工具": "非AI/通用工具", "行业": "行业动态", "动态": "行业动态",
}

# itemType → 分类标签（模型漏了分类标签时按内容类型补）
CATEGORY_BY_ITEM_TYPE = {
    "model_release": "模型发布", "product_launch": "产品更新", "tool_or_prompt": "教程/实践",
    "research_paper": "论文/研究", "industry_event": "行业动态",
    "opinion_analysis": "大佬观点", "tutorial_explainer": "教程/实践",
}

# itemType → 类别 key（结构化没给出类别时兜底）
CATEGORY_KEY_BY_ITEM_TYPE = {
    "model_release": "ai-models", "product_launch": "ai-products", "tool_or_prompt": "open-source",
    "research_paper": "paper", "industry_event": "industry",
    "opinion_analysis": "opinion", "tutorial_explainer": "ai-products",
}

# ── 主体公司（subjects 白名单；聚类与主题归并按它）─────────────────────────

ENTITIES = {
    "openai":       {"name": "OpenAI",        "aliases": ["OpenAI", "ChatGPT", "Sora", "Codex", "GPT"]},
    "anthropic":    {"name": "Anthropic",     "aliases": ["Anthropic", "Claude"]},
    "google":       {"name": "Google",        "aliases": ["Google", "DeepMind", "Gemini", "谷歌"]},
    "deepseek":     {"name": "DeepSeek",      "aliases": ["DeepSeek", "深度求索"]},
    "qwen":         {"name": "千问 Qwen",     "aliases": ["Qwen", "通义", "阿里"]},
    "kimi":         {"name": "Kimi",          "aliases": ["Kimi", "月之暗面", "Moonshot"]},
    "minimax":      {"name": "MiniMax",       "aliases": ["MiniMax", "海螺"]},
    "zhipu":        {"name": "智谱 GLM",      "aliases": ["智谱", "GLM", "Z.ai"]},
    "xai":          {"name": "xAI",           "aliases": ["xAI", "Grok"]},
    "meta":         {"name": "Meta",          "aliases": ["Meta", "Llama"]},
    "microsoft":    {"name": "Microsoft",     "aliases": ["Microsoft", "微软", "Copilot"]},
    "nvidia":       {"name": "NVIDIA",        "aliases": ["NVIDIA", "英伟达"]},
    "hugging-face": {"name": "Hugging Face",  "aliases": ["Hugging Face"]},
    "cursor":       {"name": "Cursor",        "aliases": ["Cursor", "Anysphere"]},
    "openrouter":   {"name": "OpenRouter",    "aliases": ["OpenRouter"]},
}

# ── 身份词典：防张冠李戴 ────────────────────────────────────────────────────
# 中文标题/摘要里出现这些公司（按 aliases 匹配），但原文（原标题+原摘要）里
# 没有出现过 → 标题退回原文、摘要丢弃。行业没有这个问题时可清空。

IDENTITY_LEXICON = [
    {"id": "openai",     "aliases": ["OpenAI", "ChatGPT", "GPT", "Sora", "Codex"]},
    {"id": "anthropic",  "aliases": ["Anthropic", "Claude", "Opus", "Sonnet", "Haiku"]},
    {"id": "google",     "aliases": ["Google", "DeepMind", "Gemini", "谷歌", "Veo", "NotebookLM"]},
    {"id": "deepseek",   "aliases": ["DeepSeek", "深度求索"]},
    {"id": "xai",        "aliases": ["xAI", "Grok"]},
    {"id": "meta",       "aliases": ["Meta", "Llama"]},
    {"id": "microsoft",  "aliases": ["Microsoft", "微软", "Copilot"]},
    {"id": "nvidia",     "aliases": ["NVIDIA", "英伟达"]},
    {"id": "qwen",       "aliases": ["Qwen", "通义", "千问"]},
    {"id": "hugging-face", "aliases": ["Hugging Face"]},
    {"id": "cursor",     "aliases": ["Cursor"]},
    {"id": "kimi",       "aliases": ["Kimi", "月之暗面", "Moonshot"]},
    {"id": "openrouter", "aliases": ["OpenRouter"]},
    {"id": "minimax",    "aliases": ["MiniMax"]},
    {"id": "zhipu",      "aliases": ["智谱", "GLM"]},
    {"id": "hunyuan",    "aliases": ["混元", "Hunyuan"]},
    {"id": "doubao",     "aliases": ["豆包", "Doubao", "字节跳动", "ByteDance"]},
    {"id": "mistral",    "aliases": ["Mistral"]},
    {"id": "perplexity", "aliases": ["Perplexity"]},
    {"id": "runway",     "aliases": ["Runway"]},
    {"id": "midjourney", "aliases": ["Midjourney"]},
    {"id": "stability-ai", "aliases": ["Stability AI"]},
    {"id": "elevenlabs", "aliases": ["ElevenLabs"]},
    {"id": "ollama",     "aliases": ["Ollama"]},
    {"id": "apple",      "aliases": ["苹果"]},
    {"id": "amazon",     "aliases": ["Amazon", "AWS", "亚马逊"]},
    {"id": "baidu",      "aliases": ["百度", "文心"]},
]


def _alias_pattern(alias: str) -> re.Pattern:
    """长别名优先匹配；单词型别名避免子串误伤（如 GPT 匹配到 GPT-5 没问题，Cursor 不匹配 cursor 光标）。"""
    if re.fullmatch(r"[A-Za-z0-9. -]+", alias):
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![a-z])", re.IGNORECASE)
    return re.compile(re.escape(alias))


_LEXICON_COMPILED = [(e["id"], [(a, _alias_pattern(a)) for a in sorted(e["aliases"], key=len, reverse=True)])
                     for e in IDENTITY_LEXICON]


def match_entities(text: str) -> set[str]:
    """文本里出现的主体公司 id 集合（按身份词典别名匹配）。"""
    if not text:
        return set()
    hits = set()
    for eid, pats in _LEXICON_COMPILED:
        for _, pat in pats:
            if pat.search(text):
                hits.add(eid)
                break
    return hits


def normalize_tags(raw: list, fallback_category: str | None = None) -> list[str]:
    """模型输出标签 → 词表内标签：同义词归一、去白名单外的、第一个保证是分类标签。"""
    out: list[str] = []
    for t in raw or []:
        t = TAG_SYNONYMS.get(str(t).strip(), str(t).strip())
        if t in CATEGORY_TAGS or t in TOPIC_TAGS or t in ENTITY_TAGS:
            if t not in out:
                out.append(t)
        if len(out) >= 6:
            break
    if not out or out[0] not in CATEGORY_TAGS:
        first_cat = fallback_category if fallback_category in CATEGORY_TAGS else "其他"
        out = [first_cat] + [t for t in out if t != first_cat]
    return out[:6]
