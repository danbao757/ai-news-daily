"""数据源与运行配置。"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """读取项目根目录 .env（KEY=VALUE，每行一条）。已存在的环境变量优先。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

# ── 采集 ────────────────────────────────────────────────────────────
# 采集时间窗口（小时）：每天定时跑一次 = 24
WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "24"))
# 首次运行历史为空，放宽窗口让第一期内容充实一些
FIRST_RUN_WINDOW_HOURS = 48
# 每个源最多进入加工流程的条数
MAX_PER_SOURCE = 8

# ── 日报选稿 ────────────────────────────────────────────────────────
MAX_HEADLINES = 3   # 头条条数
MAX_BRIEFING = 10   # 速览条数

# ── RSS 源（想加源就往这里加一行）──────────────────────────────────
# lang 影响后续 LLM 处理；priority 同分时用于排序参考
# X/推特无原生 RSS：需自建 RSSHub（https://docs.rsshub.app/）后加一行，如
#   {"name": "X OpenAI", "url": "http://localhost:1200/twitter/user/OpenAI", "lang": "en", "priority": 7}
RSS_SOURCES = [
    {"name": "The Decoder",   "url": "https://the-decoder.com/feed/",                                    "lang": "en", "priority": 9},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/",     "lang": "en", "priority": 8},
    {"name": "OpenAI News",   "url": "https://openai.com/news/rss.xml",                                   "lang": "en", "priority": 8},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml",                              "lang": "en", "priority": 8},
    {"name": "Ars Technica",  "url": "https://arstechnica.com/ai/feed/",                                  "lang": "en", "priority": 7},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/",                          "lang": "en", "priority": 7},
    {"name": "GitHub Blog",   "url": "https://github.blog/feed/",                                         "lang": "en", "priority": 7},
    {"name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml",                           "lang": "en", "priority": 7},
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/",                       "lang": "en", "priority": 7},
    {"name": "VentureBeat",   "url": "https://venturebeat.com/category/ai/feed/",                         "lang": "en", "priority": 6},
    {"name": "MarkTechPost",  "url": "https://www.marktechpost.com/feed/",                                "lang": "en", "priority": 6},
    {"name": "Ethan Mollick", "url": "https://www.oneusefulthing.org/feed",                               "lang": "en", "priority": 6},
    {"name": "Gary Marcus",   "url": "https://garymarcus.substack.com/feed",                               "lang": "en", "priority": 5},
    {"name": "YT DeepMind",   "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP7jMXSY2xbc3KCAE0MHQ-A", "lang": "en", "priority": 6},
    {"name": "YT Matt Wolfe", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcefcZRL2oaA_uBNeo5UOWg", "lang": "en", "priority": 5},
    {"name": "Google News AI", "url": "https://news.google.com/rss/search?q=AI+when:1d&hl=en-US&gl=US&ceid=US:en",   "lang": "en", "priority": 5},
    {"name": "机器之心",       "url": "https://www.jiqizhixin.com/rss",                                    "lang": "zh", "priority": 7},
    {"name": "量子位",         "url": "https://www.qbitai.com/feed",                                       "lang": "zh", "priority": 7},
    {"name": "雷锋网",         "url": "https://www.leiphone.com/feed",                                     "lang": "zh", "priority": 5},
    {"name": "36氪",           "url": "https://36kr.com/feed",                                             "lang": "zh", "priority": 4},
    {"name": "IT之家",         "url": "https://www.ithome.com/rss/",                                       "lang": "zh", "priority": 5},
]

# ── Hacker News（Algolia 公共 API，免key）──────────────────────────
HN_ENABLED = True
HN_MIN_POINTS = 40
HN_QUERIES = ["AI", "LLM", "OpenAI", "Claude", "Anthropic", "Gemini"]

# ── LLM（OpenAI 兼容接口，换厂商只改环境变量）─────────────────────
# DeepSeek:  LLM_BASE_URL=https://api.deepseek.com/v1       LLM_MODEL=deepseek-chat
# GLM:       LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4  LLM_MODEL=glm-4-flash（免费）
# Kimi:      LLM_BASE_URL=https://api.moonshot.cn/v1        LLM_MODEL=moonshot-v1-8k
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
LLM_BATCH_SIZE = 12  # 每次 LLM 调用处理的条目数

# ── 去重状态 ────────────────────────────────────────────────────────
SEEN_RETAIN_DAYS = 14  # 去重记忆保留天数

# ── 降级机翻 ────────────────────────────────────────────────────────
# 无 LLM_API_KEY 时用 Google gtx 免费接口翻译标题/摘要（中文源自动跳过）。
# 设 MT_FALLBACK=0 可关闭（例如接口不可达时省掉等待）。
MT_FALLBACK_ENABLED = os.environ.get("MT_FALLBACK", "1") == "1"
