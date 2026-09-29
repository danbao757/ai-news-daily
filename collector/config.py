"""数据源与运行配置。

信源分级（移植自 AIHOT）：T1 官方一手 / T1_5 准官方·高价值个人 / T2 媒体与个人。
分级决定评分门槛（两次独立评分之和 ≥ 2×门槛才精选）。
region 决定采集分工：overseas 由 GitHub Actions 海外 runner 抓（写 inbox），
domestic 由国内服务器直抓。
"""

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

SITE_NAME = "AI 日报"

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

# ── RSS 信源（加源往这里加一行；tier 与 region 见模块注释）──────────
# X/推特无原生 RSS：需自建 RSSHub（https://docs.rsshub.app/）后加一行，如
#   {"id": "x-openai", "name": "X OpenAI", "url": "http://localhost:1200/twitter/user/OpenAI",
#    "lang": "en", "tier": "T1_5", "region": "overseas", "priority": 7, "first_party": True}
RSS_SOURCES = [
    # 官方一手
    {"id": "openai-news",     "name": "OpenAI News",      "url": "https://openai.com/news/rss.xml",                                "lang": "en", "tier": "T1",   "region": "overseas", "first_party": True,  "priority": 8},
    {"id": "deepmind-blog",   "name": "DeepMind Blog",    "url": "https://deepmind.google/blog/rss.xml",                           "lang": "en", "tier": "T1",   "region": "overseas", "first_party": True,  "priority": 8},
    {"id": "github-blog",     "name": "GitHub Blog",      "url": "https://github.blog/feed/",                                      "lang": "en", "tier": "T1",   "region": "overseas", "first_party": True,  "priority": 7},
    {"id": "hf-blog",         "name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml",                           "lang": "en", "tier": "T1",   "region": "overseas", "first_party": True,  "priority": 7},
    {"id": "yt-deepmind",     "name": "YT DeepMind",      "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP7jMXSY2xbc3KCAE0MHQ-A", "lang": "en", "tier": "T1_5", "region": "overseas", "first_party": True, "priority": 6},
    # 高价值个人 / 准官方
    {"id": "simonwillison",   "name": "Simon Willison",   "url": "https://simonwillison.net/atom/everything/",                     "lang": "en", "tier": "T1_5", "region": "overseas", "first_party": False, "priority": 7},
    {"id": "ethan-mollick",   "name": "Ethan Mollick",    "url": "https://www.oneusefulthing.org/feed",                            "lang": "en", "tier": "T1_5", "region": "overseas", "first_party": False, "priority": 6},
    # 媒体与聚合
    {"id": "the-decoder",     "name": "The Decoder",      "url": "https://the-decoder.com/feed/",                                  "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 9},
    {"id": "techcrunch-ai",   "name": "TechCrunch AI",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/",  "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 8},
    {"id": "ars-technica",    "name": "Ars Technica",     "url": "https://arstechnica.com/ai/feed/",                               "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 7},
    {"id": "mit-tr",          "name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/",                         "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 7},
    {"id": "venturebeat",     "name": "VentureBeat",      "url": "https://venturebeat.com/category/ai/feed/",                      "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 6},
    {"id": "marktechpost",    "name": "MarkTechPost",     "url": "https://www.marktechpost.com/feed/",                             "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 6},
    {"id": "yt-matt-wolfe",   "name": "YT Matt Wolfe",    "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcefcZRL2oaA_uBNeo5UOWg", "lang": "en", "tier": "T2", "region": "overseas", "first_party": False, "priority": 5},
    {"id": "google-news-ai",  "name": "Google News AI",   "url": "https://news.google.com/rss/search?q=AI+when:1d&hl=en-US&gl=US&ceid=US:en", "lang": "en", "tier": "T2", "region": "overseas", "first_party": False, "priority": 5},
    {"id": "gary-marcus",     "name": "Gary Marcus",      "url": "https://garymarcus.substack.com/feed",                           "lang": "en", "tier": "T2",   "region": "overseas", "first_party": False, "priority": 5},
    # 国内源（国内服务器直抓；GitHub Actions 海外 runner 也抓得到，作为冗余）
    {"id": "jiqizhixin",      "name": "机器之心",         "url": "https://www.jiqizhixin.com/rss",                                 "lang": "zh", "tier": "T2",   "region": "domestic", "first_party": False, "priority": 7},
    {"id": "qbitai",          "name": "量子位",           "url": "https://www.qbitai.com/feed",                                    "lang": "zh", "tier": "T2",   "region": "domestic", "first_party": False, "priority": 7},
    {"id": "leiphone",        "name": "雷锋网",           "url": "https://www.leiphone.com/feed",                                  "lang": "zh", "tier": "T2",   "region": "domestic", "first_party": False, "priority": 5},
    {"id": "36kr",            "name": "36氪",             "url": "https://36kr.com/feed",                                          "lang": "zh", "tier": "T2",   "region": "domestic", "first_party": False, "priority": 4},
    {"id": "ithome",          "name": "IT之家",           "url": "https://www.ithome.com/rss/",                                    "lang": "zh", "tier": "T2",   "region": "domestic", "first_party": False, "priority": 5},
]

# ── Hacker News（Algolia 公共 API，免 key；社区信号，T2）────────────
HN_ENABLED = True
HN_MIN_POINTS = 40
HN_QUERIES = ["AI", "LLM", "OpenAI", "Claude", "Anthropic", "Gemini"]

# ── 精选门槛（移植自 AIHOT industry/selection.ts，按本站评分模型校准）──
# 每篇资料由评分模型独立打两次分（0-100），两次之和 ≥ 2×门槛才精选，
# 卡片显示两次的平均分（向下取整）。官方一手门槛低，媒体个人门槛高。
# AIHOT 原值 60/65/76 是按其评分模型校准的；glm-4-flash 对重磅新闻普遍
# 打 65-72，E2E 实测（2026-09-29，45 条）原门槛下仅 1 条精选，整体下移。
SELECTION_THRESHOLDS = {"T1": 55, "T1_5": 60, "T2": 70}
# 没入选、但平均分高于此数的条目，也用「内容理解」档写作（含推荐理由），
# 其余用便宜的「标题摘要」档。
UNDERSTAND_FLOOR = 50

# ── 聚类与热度 ──────────────────────────────────────────────────────
# 聚类只看最近 N 天的已有事件（跨日续接用）
CLUSTER_LOOKBACK_DAYS = 2
# 独立报道源数 ≥ 此值的事件才生成独立事件页
EVENT_PAGE_MIN_SOURCES = 2

# ── LLM（OpenAI 兼容接口，换厂商只改环境变量）─────────────────────
# DeepSeek:  LLM_BASE_URL=https://api.deepseek.com/v1       LLM_MODEL=deepseek-chat
# GLM:       LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4  LLM_MODEL=glm-4-flash（免费）
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
# 可选：评分/写作单独换模型（不设则用 LLM_MODEL）
SCORE_MODEL = os.environ.get("SCORE_MODEL", LLM_MODEL)
WRITE_MODEL = os.environ.get("WRITE_MODEL", LLM_MODEL)
# 免费档有速率限制：并发与请求间隔控制 + 失败退避重试
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "3"))
LLM_MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "0.5"))  # 秒，请求最小间隔
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "4"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "180"))

# ── 去重状态 ────────────────────────────────────────────────────────
SEEN_RETAIN_DAYS = 14  # 去重记忆保留天数

# ── 降级机翻 ────────────────────────────────────────────────────────
# 无 LLM_API_KEY 时用 Google 免费接口翻译标题/摘要（中文源自动跳过）。
# 设 MT_FALLBACK=0 可关闭（例如接口不可达时省掉等待）。
MT_FALLBACK_ENABLED = os.environ.get("MT_FALLBACK", "1") == "1"


def threshold_of(tier: str) -> int:
    return SELECTION_THRESHOLDS.get(tier, SELECTION_THRESHOLDS["T2"])
