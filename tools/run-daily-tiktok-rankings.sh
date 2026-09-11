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

# データ期間末 = 実際に読むTSVのDL日 - 2日（Backstageの反映遅れ。tools/data_asof.py 参照）
DATE="$(python3 tools/data_asof.py --fmt md 2>>"$LOG")"
[ -n "$DATE" ] || fail "データ期間末の判定に失敗（TSVが見つからない等）"
# 対象月 = そのデータ期間末が属する月。9/1・9/2は8月を締め続け、9/3から9月へ自動で切り替わる。
# 前月のイベント/CSVはそのまま残る（＝最終状態で凍結アーカイブ）。
MONTH="$(python3 tools/data_asof.py --fmt month 2>>"$LOG")"
[ -n "$MONTH" ] || fail "対象月の判定に失敗（TSVが見つからない等）"
YM="${MONTH/-/}"
# 対象月のイベントがevents.jsonに無ければ前月から複製して用意する
python3 tools/ensure_month_events.py --month "$MONTH" 2>>"$LOG" || fail "対象月イベントの用意に失敗"
# サイト側の表示期間(period_end)も同じ日付に揃える
python3 tools/data_asof.py --set-events "tiktok-${YM}-newcomer,tiktok-${YM}-rise" \
  >/dev/null 2>>"$LOG" || fail "period_end の更新に失敗"
say "===== 開始 (month=$MONTH date=$DATE) ====="

# 1. ビギナー（当月10万pt到達で卒業→7日猶予後に自動で掲載終了）
BEG="$(python3 tools/daily_beginner.py --month "$MONTH" --floor 1000 --date "$DATE" --bare 2>>"$LOG")"
[ -n "$BEG" ] || fail "ビギナー生成失敗（データTSVが見つからない等）"

# 2. ⚡️DCL RISE⚡️（中間層＋当月10万pt超えは即時ピック）
RISE="$(python3 tools/daily_rise.py --month "$MONTH" --floor 1 --date "$DATE" --bare 2>>"$LOG")"
[ -n "$RISE" ] || fail "RISE生成失敗（データTSVが見つからない等）"

# 2.5 スタンプラリー更新（snapshot確定後・build前）：名簿マージ→JSON再生成→_manifest.json最新化＋stamp Pages push。
#     build.py はこの _manifest を読んで獲得ptをランキングに合算する。
#     失敗しても非致命（前回の _manifest で build を続行＝ランキング公開は止めない）。
if ! "$HOME/Claude/stamp-rally/tools/run-daily.sh" >>"$LOG" 2>&1; then
  say "⚠️ スタンプラリー更新に失敗（合算は前回値のまま build を続行）"
else
  say "スタンプラリー更新OK（合算用 _manifest 最新化）"
fi
# 合算用のスタンプptを repo内 data/stamp_points.json へ同梱（GitHub Actionsのランナーでも読めるように）。
# 失敗しても非致命（前回の stamp_points.json で build 続行）。
python3 tools/make_stamp_points.py >>"$LOG" 2>&1 && say "stamp_points.json 更新OK" \
  || say "⚠️ stamp_points.json 生成に失敗（前回値のまま build 続行）"

# 3. サイト再生成（両ランキングまとめて1回。スタンプpt合算を含む）
python3 build.py >>"$LOG" 2>&1 || fail "build失敗"

# 4. 変更があれば push（1回）
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
  if git add -A && git commit -q -m "daily: ビギナー＋RISE ランキング更新 ($MONTH / $DATE)" && git push -q >>"$LOG" 2>&1; then
    say "push完了"
  else
    fail "git push失敗（ローカルは更新済み）"
  fi
else
  say "変更なし（pushスキップ）"
fi

say "===== 完了 ====="
# 5. Slack本文を「親」と「スレッド返信」の2つに分けて出力する。
#    区切りは ===THREAD=== の1行。タスク側は
#      親  = マーカーより前  → conversations_add_message（thread_ts なし）
#      詳細 = マーカーより後 → 同ツールに親の ts を thread_ts で指定
#    で2回投稿する。--bare 出力は「1行目=見出し / 2行目=URL / 3行目=空 / 4行目以降=詳細」。
beg_head="$(printf '%s\n' "$BEG" | head -2)"   # 🌱見出し＋URL
beg_body="$(printf '%s\n' "$BEG" | tail -n +4)" # 順位変動・卒業・掲載終了
rise_head="$(printf '%s\n' "$RISE" | head -2)"  # ⚡️見出し＋URL
rise_body="$(printf '%s\n' "$RISE" | tail -n +4)" # 順位変動・新規RISE入り

# --- 親メッセージ（短く：見出し＋メンション＋2つのURLだけ） ---
printf '%s\n' "📊 TikTok LIVE ランキング更新（${DATE}時点）"
printf '%s\n\n' "<@U0A6WU3P3LL>"
printf '%s\n\n' "$beg_head"
printf '%s\n' "$rise_head"

printf '\n%s\n' "===THREAD==="

# --- スレッド返信（詳細：メンションは付けない） ---
printf '%s\n' "🌱 DCLビギナーランキング"
printf '%s\n\n' "$beg_body"
printf '%s\n' "⚡️DCL RISE⚡️"
printf '%s\n' "$rise_body"
