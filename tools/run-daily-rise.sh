#!/bin/bash
# ⚡️DCL RISE⚡️ 日次更新（スケジュールタスク tiktok-rise-ranking-daily から呼ぶ）
#   最新TSV(=tiktok-creator-data-daily 10:06の成果物)を読む → CSV生成＋順位差分
#   → build → git push まで行い、最後に「Slack投稿本文」だけを標準出力に出す。
#   実際のSlack投稿はスケジュールタスク側が MCP(conversations_add_message) で ito_sukeaki名義で行う。
#   診断ログは tools/daily-rise.log と標準エラーへ。標準出力はSlack本文のみ。
set -uo pipefail
REPO="$HOME/Claude/event-rankings"
cd "$REPO" || { echo "❌ event-rankings が見つかりません"; exit 1; }
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$HOME/.local/node/bin:$PATH"

LOG="$REPO/tools/daily-rise.log"
say(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

LOCK="$REPO/tools/.rise.lock"
if ! mkdir "$LOCK" 2>/dev/null; then say "既に実行中のため中止"; echo "（既に実行中のためスキップ）"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

DATE="$(TZ=UTC date -v-1d '+%-m/%d')"   # 前日(UTC)=データ期間末
say "===== 開始 (date=$DATE) ====="

# 1. ランキング生成＋順位差分（Slack本文は stdout、診断は stderr→ログ）
MSG="$(python3 tools/daily_rise.py --month 2026-08 --floor 1 --date "$DATE" 2>>"$LOG")"
if [ -z "$MSG" ]; then
  say "❌ 生成失敗（TSVなし等）"
  echo "<@U0A6WU3P3LL>"
  echo "⚠️ ⚡️DCL RISE⚡️ 自動更新に失敗（データTSVが見つからない等）。サイトは更新していません。"
  exit 1
fi

# 2. サイト再生成
if ! python3 build.py >>"$LOG" 2>&1; then
  say "❌ build失敗"
  echo "<@U0A6WU3P3LL>"
  echo "⚠️ ⚡️DCL RISE⚡️ build失敗。サイトは更新していません。"
  exit 1
fi

# 3. 変更があれば push
if ! git diff --quiet || ! git diff --cached --quiet; then
  if git add -A && git commit -q -m "daily: RISE更新 ($DATE)" && git push -q >>"$LOG" 2>&1; then
    say "push完了"
  else
    say "❌ push失敗"
    echo "<@U0A6WU3P3LL>"
    echo "⚠️ ⚡️DCL RISE⚡️ git push失敗。ローカルは更新済みですが公開反映していません。"
    exit 1
  fi
else
  say "変更なし（pushスキップ）"
fi

say "===== 完了 ====="
# 標準出力にSlack本文（これをスケジュールタスクがそのまま投稿する）
printf '%s\n' "$MSG"
