#!/bin/sh
# 自有 Linux 主機用：由 cron 呼叫。設定寫在同目錄的 .env（權限請設 600）
cd "$(dirname "$0")" || exit 1
[ -f .env ] && . ./.env
export FINMIND_TOKEN DATA_DIR
exec python3 update.py >> update.log 2>&1
