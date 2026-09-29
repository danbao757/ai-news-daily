#!/usr/bin/env bash
# 国内云服务器定时同步脚本（crontab 09:30，等 Actions 08:13 写完 inbox）：
#   拉取仓库 → 跑完整管线（消费 inbox + 直抓国内源 + LLM 加工/聚类）→ 回推
# GitHub 直连不通时自动改推 Gitee 镜像（镜像再同步回 GitHub，或服务器侧
# 配置双 remote 各推一次）。
#
# 首次部署见同目录 README.md。日志：deploy/server/sync.log

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/ai-news-daily}"
LOG="${REPO_DIR}/deploy/server/sync.log"
BRANCH="${BRANCH:-main}"
# 回推通道：先试 GitHub，不通走 Gitee（都写成仓库 remote）
PUSH_PRIMARY="${PUSH_PRIMARY:-origin}"
PUSH_FALLBACK="${PUSH_FALLBACK:-gitee}"

cd "$REPO_DIR"
mkdir -p deploy/server
exec >>"$LOG" 2>&1
echo "===== $(date '+%F %T') sync start ====="

# .env 与 venv 就位（首次部署后长期存在）
set -a; [ -f .env ] && . ./.env; set +a
# shellcheck disable=SC1091
[ -f venv/bin/activate ] && . venv/bin/activate || true

git pull --rebase "$PUSH_PRIMARY" "$BRANCH" || {
  echo "[warn] GitHub 拉取失败，试 Gitee"
  git pull --rebase "$PUSH_FALLBACK" "$BRANCH"
}

# 出刊（当天已出刊时 pipeline 自己跳过，幂等）
python -m collector.pipeline

# 回推：inbox 已消费删除 + 新刊数据
if git status --porcelain data | grep -q .; then
  git add data
  git commit -m "chore: issue $(TZ=Asia/Shanghai date +%F)"
  if git push "$PUSH_PRIMARY" "$BRANCH"; then
    echo "push via $PUSH_PRIMARY ok"
  else
    echo "[warn] GitHub 推送失败，改推 $PUSH_FALLBACK"
    git push "$PUSH_FALLBACK" "$BRANCH"
  fi
else
  echo "无数据变更，跳过推送"
fi

echo "===== $(date '+%F %T') sync done ====="
