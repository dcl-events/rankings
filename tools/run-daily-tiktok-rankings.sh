#!/bin/bash
# TikTok LIVE ランキング 日次更新（ビギナー＋⚡️DCL RISE⚡️を1本のSlack投稿にまとめる）
#   スケジュールタスク tiktok-beginner-ranking-daily から呼ばれる。
#   最新TSV(=tiktok-creator-data-daily 10:06の成果物)を読む → 両ランキングのCSV生成＋順位差分
#   → build 1回 → git push 1回 → 最後に「まとめSlack投稿本文」だけを標準出力に出す。
#   実際の投稿はタスク側が MCP(conversations_add_message) で ito_sukeaki名義で行う。
#   診断ログは tools/daily-rankings.log と標準エラーへ。標準出力はSlack本文のみ。
set -uo pipefail
REPO="$HOME/Claude/event-rankings"
cd "$REPO" || { echo "❌ event-rankings が見つかりません"; exit 1; }
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$HOME/.local/node/bin:$PATH"

LOG="$REPO/tools/daily-rankings.log"
say(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
fail(){ say "❌ $1"; echo "<@U0A6WU3P3LL>"; echo "⚠️ TikTok LIVEランキング 自動更新に失敗（$1）。サイトは更新していません。"; exit 1; }

LOCK="$REPO/tools/.rankings.lock"
if ! mkdir "$LOCK" 2>/dev/null; then say "既に実行中のため中止"; echo "（既に実行中のためスキップ）"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

DATE="$(TZ=UTC date -v-1d '+%-m/%d')"   # 前日(UTC)=データ期間末
say "===== 開始 (date=$DATE) ====="

# 1. ビギナー（当月10万pt到達で卒業→7日猶予後に自動で掲載終了）
BEG="$(python3 tools/daily_beginner.py --month 2026-08 --floor 1000 --date "$DATE" --bare 2>>"$LOG")"
[ -n "$BEG" ] || fail "ビギナー生成失敗（データTSVが見つからない等）"

# 2. ⚡️DCL RISE⚡️（中間層＋当月10万pt超えは即時ピック）
RISE="$(python3 tools/daily_rise.py --month 2026-08 --floor 100000 --date "$DATE" --bare 2>>"$LOG")"
[ -n "$RISE" ] || fail "RISE生成失敗（データTSVが見つからない等）"

# 3. サイト再生成（両ランキングまとめて1回）
python3 build.py >>"$LOG" 2>&1 || fail "build失敗"

# 4. 変更があれば push（1回）
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
  if git add -A && git commit -q -m "daily: ビギナー＋RISE ランキング更新 ($DATE)" && git push -q >>"$LOG" 2>&1; then
    say "push完了"
  else
    fail "git push失敗（ローカルは更新済み）"
  fi
else
  say "変更なし（pushスキップ）"
fi

say "===== 完了 ====="
# 5. まとめSlack本文（これをスケジュールタスクがそのまま投稿する）
printf '%s\n' "📊 TikTok LIVE ランキング更新（${DATE}時点）"
printf '%s\n\n' "<@U0A6WU3P3LL>"
printf '%s\n\n' "$BEG"
printf '%s\n' "$RISE"
