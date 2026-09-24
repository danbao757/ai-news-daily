# AI 日报（ai-news-daily）

每日自动生成的全网 AI 资讯日报站。复刻「蛛网之上 / aihot.news」的轻量版：

```
RSS + Hacker News 采集 ──→ 去重 ──→ LLM 加工（中文标题/摘要/分类/评分）──→ 每日一期
                                                                        │
                                              Astro 静态站 ←── data/issues/*.json
```

## 项目结构

```
ai-news-daily/
├── collector/            # Python 数据管线
│   ├── config.py         #   数据源、LLM、选稿配置（加源改这里）
│   ├── sources.py        #   RSS + Hacker News 采集
│   ├── dedup.py          #   URL + 标题相似度去重
│   ├── llm.py            #   LLM 批量加工（OpenAI 兼容接口）
│   └── generate.py       #   主流程入口
├── data/
│   ├── issues/           # 每日日报 JSON（建站数据，随 git 保存）
│   └── seen.json         # 去重记忆（最近 14 天）
├── site/                 # Astro 静态站点
└── .github/workflows/daily.yml   # 每天 08:05（北京时间）自动生成并部署
```

## 本地运行

```bash
# 1. 安装 Python 依赖
pip install -r collector/requirements.txt

# 2. 生成今日日报（未配置 LLM key 时降级为原始条目，不翻译不评分）
python -m collector.generate

# 3. 启动前端
cd site && npm install && npm run dev
```

## LLM 配置（推荐配置，管线核心）

任何 OpenAI 兼容接口都可以，环境变量三件套：

| 厂商 | LLM_BASE_URL | LLM_MODEL | 费用参考 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 约 ¥1-3/月 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | 免费 |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | 便宜 |

```bash
export LLM_API_KEY=sk-xxx
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat
python -m collector.generate   # FORCE=1 前缀可覆盖重生成当日
```

Windows 下不想每次 export，可在项目根目录建 `.env` 文件（已被 .gitignore 忽略，不会提交）：

```
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

## 部署到 GitHub Pages（免费全自动）

1. 在 GitHub 新建仓库并推送代码：
   ```bash
   git init && git add -A && git commit -m "init: ai-news-daily"
   git remote add origin git@github.com:<用户名>/<仓库名>.git
   git push -u origin main
   ```
2. 仓库 Settings → Secrets and variables → Actions：
   - 新增 Secret：`LLM_API_KEY`
   - （可选）新增 Variables：`LLM_BASE_URL`、`LLM_MODEL`
3. 仓库 Settings → Pages → Source 选择 **GitHub Actions**
4. 修改 `site/astro.config.mjs` 中的 `site`（和 `base: '/仓库名'`，如果用项目站）
5. 之后每天北京时间 08:05 自动采集、生成、部署；也可在 Actions 页手动触发

> 也可以把 `site/` 直接导入 Vercel / Cloudflare Pages（构建命令 `npm run build`，输出目录 `dist`），
> GitHub Actions 只负责生成数据和提交。

## 想扩展？

- **加 RSS 源**：`collector/config.py` 的 `RSS_SOURCES` 加一行即可
- **抓 X/推特、微信公众号**：自建 [RSSHub](https://docs.rsshub.app/) 把目标转成 RSS 再加进来
- **升级成实时聚合站（aihot.news 形态）**：管线已就绪，把 `generate.py` 的日批改成 cron 每 15 分钟增量跑，数据写 PostgreSQL，前端换 Next.js 动态渲染即可

## 版权说明

内容来自公开 RSS 与 API，仅保存标题、摘要与原文链接，不存储全文；版权归原作者所有。
