# 国内服务器部署（v2 管线）

Actions（海外 runner，免费）负责抓海外源写 `data/inbox/`；本机（国内服务器，
LLM 国内直连）消费 inbox、直抓国内源、完成 LLM 加工与聚类，成果 push 回仓库，
push 触发 GitHub Actions 自动构建部署 Pages。

## 首次部署

```bash
# 1. 克隆（GitHub 不通就先从 Gitee 镜像克隆，或本地上传）
git clone https://github.com/danbao757/ai-news-daily.git ~/ai-news-daily
cd ~/ai-news-daily

# 2. 探测回推通道（服务器 → GitHub）
git ls-remote https://github.com/danbao757/ai-news-daily.git HEAD \
  && echo "GitHub 直连 OK" \
  || echo "不通：需配 Gitee 镜像中转"

# GitHub 不通时：在 Gitee 建同仓镜像并加 remote
# git remote add gitee https://gitee.com/<你>/ai-news-daily.git
# （Gitee 仓库开启「强制同步」或由本脚本推送后手动同步回 GitHub）

# 3. Python 环境与依赖
python3 -m venv venv
. venv/bin/activate
pip install -r collector/requirements.txt

# 4. 配置 key（智谱/DeepSeek 国内直连）
cp .env.example .env 2>/dev/null || true
vim .env   # LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=...

# 5. 手动跑一次验证（当天已出刊会跳过，可 FORCE=1 强制重跑）
python -m collector.pipeline

# 6. 定时任务（09:30 = Actions 08:13 出 inbox + 09:47 备份之后）
crontab -e
# 30 9 * * * REPO_DIR=$HOME/ai-news-daily bash $HOME/ai-news-daily/deploy/server/sync.sh
```

## 接管后关掉 Actions 上的过渡管线

仓库 Settings → Secrets and variables → Actions → Variables 加
`STOPGAP_PIPELINE=0`，fetch 工作流即退化为「只写 inbox」，LLM 加工全部由本机完成。

## 日志与排障

- 运行日志：`deploy/server/sync.log`
- 断点续跑：中断后重跑 `python -m collector.pipeline`，已完成条目不重复调用 LLM
- 当天重出刊：`FORCE=1 python -m collector.pipeline`（沿用原期号）
