#!/bin/bash
# DCLビギナーランキング 日次ルーティン（毎日10:30想定）
#   最新TSV(=10:00の creator data ルーティン成果物)を読む → CSV生成＋順位差分
#   → build → git push → Slack(#tiktoklive立ち上げ)へ URL＋上を抜いた人 を通知
# 10:00の creator-data ルーティンとは別プロセス・読むだけなので競合しない。
set -uo pipefail
REPO="$HOME/Claude/event-rankings"
cd "$REPO" || exit 1
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$HOME/.local/node/bin:$PATH"

LOG="$REPO/tools/daily-beginner.log"
say(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

LOCK="$REPO/tools/.beginner.lock"
if ! mkdir "$LOCK" 2>/dev/null; then say "既に実行中のため中止"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

DATE="$(TZ=UTC date -v-1d '+%-m/%d')"   # 前日(UTC)=データ期間末
say "===== 開始 (date=$DATE) ====="

# 1. ランキング生成＋順位差分（Slack本文を取得）
MSG="$(python3 tools/daily_beginner.py --month 2026-08 --floor 1000 --date "$DATE" 2>>"$LOG")"
if [ -z "$MSG" ]; then say "❌ 生成失敗（TSVなし等）"; exit 1; fi

# 2. サイト再生成
python3 build.py >>"$LOG" 2>&1 || { say "❌ build失敗"; exit 1; }

# 3. 変更があれば push
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A && git commit -q -m "daily: ビギナーランキング更新 ($DATE)" \
    && git push -q >>"$LOG" 2>&1 && say "push完了" || { say "❌ push失敗"; exit 1; }
else
  say "変更なし（pushスキップ）"
fi

# 4. Slack通知（失敗しても致命にしない＝サイト更新は成立させる）
if printf '%s' "$MSG" | python3 tools/post_slack.py >>"$LOG" 2>&1; then
  say "Slack投稿OK"
else
  say "⚠️ Slack投稿失敗（Botが #tiktoklive立ち上げ に未招待の可能性。/invite @pococha_event）"
fi

say "===== 完了 ====="
