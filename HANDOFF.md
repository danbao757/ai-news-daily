# AI 日报（ai-news-daily）· 项目交接文档

> 本文档由 2026-09-24 的开发会话整理于 2026-09-28，供在其他环境接续开发使用。
> 2026-09-28 第二次开发会话已更新：新增站内搜索、RSS 订阅、2 个信源、软文过滤，并修复站内链接 404 bug。
> 项目已**完整上线并自动化运行**，接手即可迭代，无需从头搭建。

| 关键信息 | 值 |
|---|---|
| 线上地址 | https://danbao757.github.io/ai-news-daily/ |
| 代码仓库 | https://github.com/danbao757/ai-news-daily （**public**） |
| 自动化 | GitHub Actions，每天北京时间 **08:05**（cron `5 0 * * *` UTC） |
| 当前状态 | 已出至**第 5 期**（2026-09-24 ~ 09-28），工作流连续成功 |
| 站点功能 | 首页 / 往期归档 / **站内搜索** `/search` / **RSS 订阅** `/rss.xml` |
| 本地路径 | `D:\ai-news-daily` |

---

## 1. 项目背景与定位

用户想复刻两个参考站：

- **蛛网之上** https://tiaozhuxiansheng.com/news/ —— 每日一期的人工精选 AI 日报（Astro 静态站）
- **AIHOT** https://aihot.news/all —— 实时聚合、AI 评分 0-100、多源聚类

当初给出两条路线，用户选定 **路线 A：轻量日报版**（本项目的形态）。路线 B（实时聚合站）作为升级路径保留，见 §8。

**产品逻辑**：每天自动从全网公开信源抓取最近 24 小时的 AI 新闻 → 去重 → LLM 加工（中文标题、摘要、分类、重要度评分）→ 选出头条 3 条 + 速览 10 条 → 生成静态站自动部署。页面上每条新闻点击跳转**原文出处**，本站只存标题/摘要/链接，不存正文（版权安全）。

## 2. 架构与数据流

```
RSS（11 源）─┐
             ├→ 采集(sources.py) → 每源截8条 → 去重(dedup.py, 14天记忆)
Hacker News ─┘        │  URL精确 + 标题3-gram Jaccard≥0.55
                      ↓
               LLM 批量加工(llm.py, 12条/次, OpenAI兼容接口)
                      ↓  中文标题/摘要/分类(7类)/评分(0-100)/keep + 软文过滤
               选稿(generate.py): (score, priority) 降序
                      ↓  头条3 + 速览10
               data/issues/YYYY-MM-DD.json（随 git 保存，即历史档案）
                      ↓
               Astro 构建(site/) + Pagefind 索引 → GitHub Pages
```

每日定时由 `.github/workflows/daily.yml` 驱动：生成 → git 提交数据 → build → deploy。

## 3. 目录结构与关键文件

```
ai-news-daily/
├── collector/               # Python 数据管线
│   ├── config.py            # ★ 所有可调参数（加源/改窗口/换LLM厂商都改这里）
│   ├── sources.py           # RSS(feedparser) + HN(Algolia API)
│   ├── dedup.py             # SeenStore 去重，落盘 data/seen.json
│   ├── llm.py               # LLM 批量加工 + 无 key 降级 _fallback()
│   └── generate.py          # 主入口 python -m collector.generate
├── data/
│   ├── issues/*.json        # 每期日报数据（Issue 结构见下）
│   └── seen.json            # 去重记忆（14 天滚动）
├── site/                    # Astro 5 静态站
│   ├── astro.config.mjs     # site + base 已按 GitHub Pages 配好
│   └── src/
│       ├── lib/issues.ts    # getIssues() 读项目根 data/issues
│       ├── lib/url.ts       # withBase()：站内链接拼 base 前缀（防 404）
│       ├── pages/           # index / archive / issue/[date] / search / rss.xml.js
│       ├── components/      # IssueView.astro, CategoryChip.astro
│       ├── layouts/         # Layout.astro（导航含"搜索"，head 含 RSS 自动发现）
│       └── styles/global.css# 全部设计变量与组件样式（含 Pagefind UI 融合）
└── .github/workflows/daily.yml
```

构建命令 `npm run build` = `astro build && pagefind --site dist`（pagefind 为 devDependency，
构建后生成 `dist/pagefind/` 搜索索引；搜索页运行时从 `pagefind-ui.js` 加载 UI）。

### 关键实现细节（接手必读）

- **config.py**：`WINDOW_HOURS=24`（首期为 48）；`MAX_PER_SOURCE=8`；`MAX_HEADLINES=3` / `MAX_BRIEFING=10`；`HN_MIN_POINTS=40`；LLM 三件套读环境变量 `LLM_API_KEY` / `LLM_BASE_URL`（默认 `https://api.deepseek.com/v1`）/ `LLM_MODEL`（默认 `deepseek-chat`）。**自动加载项目根 `.env`**（`os.environ.setdefault`，真实环境变量优先；`.env` 已被 gitignore）。
- **RSS_SOURCES**（11 个，priority 用于同分排序）：The Decoder(9)、TechCrunch AI(8)、Ars Technica(7)、MIT Tech Review(7)、VentureBeat(6)、MarkTechPost(6)、机器之心(7)、量子位(7)、雷锋网(5)、36氪(4)、IT之家(5)。**加源 = 在此数组加一行**（注意 MIT TR 是综合科技源，非 AI 条目靠 LLM keep=false 过滤，降级模式下会混入非 AI 新闻）。
- **dedup.py**：标题字符 3-gram 集合的 Jaccard 相似度 ≥0.55 判重（中英文通用，无外部依赖）；`is_dup(item, ignore_after)` 的 `ignore_after` 参数专为 FORCE 重跑当日设计（忽略今天记入的记忆，但保留更早的）。
- **llm.py**：要求模型返回 JSON 数组，字段 `id/title_zh/summary_zh/category/tags/score/keep`；分类白名单 `["模型","产品","行业","论文","开源","政策","观点"]`，未匹配落 `未分类`；评分锚点：90+ 行业突破 / 75-89 重要发布 / 60-74 有影响的更新 / 40-59 例行 / <40 边缘。失败或无 key 走 `_fallback()`（原标题、score 50、keep True）。**软文过滤**：`_JUNK_TITLE_RE` 命中招聘/行情/促销/付费课程类标题强制 keep=False，LLM 与降级路径共用，加词改正则即可。
- **rss.xml.js**：Astro 静态端点，每期一条 digest item（HTML 摘要已实体转义）。**端点必须导出大写 `GET` 并返回 `new Response()`**——小写 `get` 或返回 `{body}` 会被静默跳过（见 §7）。
- **generate.py**：当日 JSON 已存在则跳过；`FORCE=1 python -m collector.generate` 覆盖重跑（**沿用原期号**，不递增）。
- **Issue JSON 结构**：`{issue, date, generated_at, stats{collected,duplicates,selected,sources}, headlines[], briefing[]}`，条目字段 `title_zh/title_orig/summary_zh/category/tags/score/source/url/published_at`。
- **site/src/lib/issues.ts**：数据目录解析为 `../../../data/issues`（lib→src→site→项目根，**共三级**）。曾因写成四级导致 `issue/[date]` 路由生成 0 页面——动目录结构时务必核对。

## 4. 本地开发

```bash
cd D:\ai-news-daily

# Python 端（Windows 必须加 -X utf8，否则 GBK 控制台中文乱码）
pip install -r collector/requirements.txt
python -X utf8 -m collector.generate           # 生成今日（已存在则跳过）
FORCE=1 python -X utf8 -m collector.generate   # 覆盖重跑当日

# 前端
cd site
npm install
npm run dev        # 开发服 http://localhost:4321
npm run build      # 产出到 site/dist
```

本机环境备忘：

- **这台机器直连 GitHub 会被重置**，git push 需走本地 Clash 代理（7897 端口）：
  ```bash
  git -c http.proxy=http://127.0.0.1:7897 push origin main
  # 或一劳永逸：git config --global http.https://github.com.proxy http://127.0.0.1:7897
  ```
- **机器之心、量子位的 RSS 本机连不上**（机器网络问题），代码里保留着——GitHub Actions 的海外 runner 抓取正常（量子位线上每期都有出稿）。本机跑只会告警跳过，不影响其他源。
- VentureFeed 偶发 429 限流，属对方站限速，忽略即可。
- 本机会话的 bash 每条命令后 cwd 会重置，脚本里请用绝对路径或每次 `cd`。

## 5. 部署与运维

- **GitHub Pages**：仓库 Settings → Pages → Source 已设为 GitHub Actions（API 里 `build_type=workflow`）。`astro.config.mjs` 已配 `site: 'https://danbao757.github.io'` + `base: '/ai-news-daily'`——**换部署方式/域名必须同步改这两项**，否则资源 404。
- **手动触发部署**：Actions 页选 daily → Run workflow；或 API `POST /repos/danbao757/ai-news-daily/actions/workflows/daily.yml/dispatches`（body `{"ref":"main"}`）。
- **仓库是 public 的原因**：GitHub 免费账户私有仓库不能开 Pages。若要转私有，改用 Vercel/Cloudflare Pages 部署 `site/`（构建命令 `npm run build`，输出 `dist`），Actions 只负责生成数据。
- **推代码认证**：本机 Git 凭证管理器已存 danbao757 的 GitHub 凭证；MCP 的 GitHub 工具未认证，调 API 时用 `git credential fill` 取 token。

## 6. ⚠️ 唯一未完成项：LLM key

线上目前是**降级模式**（无 `LLM_API_KEY`）：英文原标题、无摘要、分类全"未分类"、评分统一 50。管线本身已就绪，配置后第二天自动变完整版，无需改代码：

1. 取一个 key：智谱 `glm-4-flash` **免费**（`https://open.bigmodel.cn`）或 DeepSeek（约 ¥1-3/月）
2. 仓库 Settings → Secrets and variables → Actions → New repository secret：名 `LLM_API_KEY`
3. （可选，非 DeepSeek 时）加 Variables：`LLM_BASE_URL`、`LLM_MODEL`

本地测试则在 `D:\ai-news-daily\.env` 写同样三行后 `FORCE=1` 重跑当日。

## 7. 踩过的坑（避免重蹈）

| 坑 | 现象 | 解法 |
|---|---|---|
| issues.ts 相对路径多一级 | build 成功但 `/issue/[date]` 生成 0 页 | 数据目录必须是三级 `../../../data/issues` |
| FORCE 重跑期号递增 | 同一天变成第 2 期 | 覆盖时沿用 JSON 里存的 `issue` 号 |
| FORCE 重跑被自家去重吃掉 | 31 条只剩 3 条"新" | `is_dup` 加 `ignore_after`（今日 0 点） |
| GBK 控制台传中文 | curl -d 内联 JSON 报 "Problems parsing JSON" | 中文载荷写临时文件 `--data-binary @file`，Python 加 `-X utf8` |
| GitHub 直连失败 | push 时 Connection was reset | 走 Clash 代理 7897 |
| GitHub cron 延迟 | 比预定时间晚几分钟到几十分钟 | 正常现象，非故障；超 2-3 小时未跑可手动 workflow_dispatch 补 |
| 站内链接缺 base 前缀 | 线上点"往期"跳 `github.io/archive` 404 | Astro 不自动改写裸 `href="/x"`；一律 `withBase('/x')`（lib/url.ts） |
| Astro 5 端点小写 get / 返回 {body} | build 无报错但 rss.xml 静默不生成，日志有 "No API Route handler ... Found handlers: get" | 端点导出大写 `GET` 且 `return new Response(xml)` |
| pagefind.js 是 ESM | 经典 `<script>` 加载报 "Cannot use 'import.meta outside a module" | Default UI 加载 `pagefind/pagefind-ui.js`（经典脚本、挂 window.PagefindUI）；`pagefind.js` 是模块入口别直接用 |
| 搜索摘录混入徽章/评分/来源噪音 | 结果摘录夹杂"未分类 ↗ 50" | 徽章/评分/来源/统计行加 `data-pagefind-ignore`，正文与标题保留索引 |

## 8. 建议下一步（路线图）

**短期**
- [ ] 配置 `LLM_API_KEY`（见 §6，唯一阻塞完整体验的事）
- [x] 加信源：MIT Tech Review、MarkTechPost（2026-09-28）；X/微信公众号需自建 [RSSHub](https://docs.rsshub.app/) 转 RSS
- [x] 站内搜索：Pagefind 已接入（2026-09-28），`/search`
- [ ] 自定义域名：Pages 加 CNAME + 改 `astro.config.mjs` 的 `site`（去掉 `base`）
- [x] 输出每日 RSS feed（2026-09-28），`/rss.xml`；邮件订阅可接 [Follow.it / Feedburner 类服务](https://follow.it)

**中期**
- [x] 标题党过滤：`_JUNK_TITLE_RE` + prompt 规则（2026-09-28）
- [ ] 多源聚类：同一事件多个源报道时合并展示"另有 N 家信源报道"（aihot.news 的玩法）
- [ ] 数据丰富后做趋势页：每周/每月标签热度、来源分布图

**长期（升级路线 B：实时聚合站）**
- cron 从每天一次改为每 15 分钟增量跑；数据从 JSON 文件迁 PostgreSQL；前端换 Next.js 动态渲染 + ISR；可加缓存与图片代理。管线代码（采集/去重/LLM）可直接复用。

## 9. 设计规范速查（site/src/styles/global.css）

- 底色 `--bg: #faf9f7`（暖纸白）、正文 `--ink: #1c1917`、强调 `--accent: #dc2622`（红）
- 正文栏最大宽度 **720px**，刊头「AI 日报」+「本期 / 往期」导航
- 分类徽章配色：模型 `#2563eb` · 产品 `#7c3aed` · 行业 `#d97706` · 论文 `#0d9488` · 开源 `#16a34a` · 政策 `#dc2626` · 观点 `#64748b`
- 头条 = 大卡片（徽章 + 标签 + 链接标题 + 摘要 + 评分 + 来源↗）；速览 = 行列表（评分列 + 标题 + 徽章 + 来源）
- 页面结构：首页（最新一期）/ archive（往期列表）/ issue/[date]（单期，getStaticPaths 从 JSON 生成）

## 10. 历史决策记录（为什么这么做）

- **路线 A 而非 B**：用户明确选择轻量日报版——零服务器成本、静态站即档案、git 历史即数据历史；实时版留作升级路径
- **JSON 文件而非数据库**：静态化的极致——无需 DB 服务，`data/issues/*.json` 天然版本化、可回滚、Pages 构建直接读
- **3-gram Jaccard 去重**：中英文通用、零依赖、阈值 0.55 经验值；跨语言同事件不合并（留给未来的聚类功能）
- **只存标题+摘要+链接**：规避版权风险；摘要由 LLM 生成而非复制原文
- **评分锚点制**（90/75/60/40）：给 LLM 明确参照，避免分数漂移；展示端同分时按信源 priority 排序
- **仓库转 public**：免费账户私有仓库无 Pages；数据仅含公开新闻链接，无敏感信息
