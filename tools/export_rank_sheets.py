#!/usr/bin/env python3
"""RISE1/2/3の当日ランキングを スプレッドシート「TikTokLIVEハイタッチ確認」の
RISE1 / RISE2 / RISE3 タブへ書き出す（毎朝の洗い替え）。

  ~/Claude/pococha/.venv/bin/python tools/export_rank_sheets.py [--league rise1,rise2,rise3]
                                                               [--dry-run] [--month 2026-11]

列（1行目=最終更新、2行目=見出し、3行目〜=データ。他タブと同じ体裁）:
  ライバー名 / バックステージリンク / Liny URL / データ期間 / クリエイターID /
  クリエイターのユーザー名 / 当日順位（卒業者はスプシのみ） / 前日順位 / ポイント

・順位は各リーグの snapshot（daily_rise*.py が毎朝書く）をそのまま使う。
  **snapshot はクリア（卒業）した人も含んだ順位**＝サイトはクリア者を上部の別枠に
  出して繰り上げるが、このシートでは卒業者も順位に含めたまま載せる（ユーザー指示）。
・前日順位は data/sheet_rank_prev.json に前回書き出した順位を持って比較する。
  同じデータ期間で再実行しても前日順位がズレないように、1世代前も保持する。
  状態ファイルが無い初回は、git履歴の1つ前の snapshot から拾う。
・ライバー名/リンク/ID等は最新TSV（tiktok-automation/out/creator_data_*.tsv）をIDで突合。
"""
import argparse
import csv
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
CREDS = "/Users/sukeaki.ito/Claude/pococha/service_account.json"
SPREADSHEET_ID = "1A-WSX4mteR-E5kY8V82dTUqoTcD0GDLA0Uq0qiDTzh4"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
STATE = os.path.join(DATA, "sheet_rank_prev.json")
JST = timezone(timedelta(hours=9))

HEADER = ["ライバー名", "バックステージリンク", "Liny URL", "データ期間", "クリエイターID",
          "クリエイターのユーザー名", "当日順位（卒業者はスプシのみ）", "前日順位", "順位変動",
          "ポイント"]
LINK_COLS = ("バックステージリンク", "Liny URL")
C_CID = HEADER.index("クリエイターID")
C_PREV = HEADER.index("前日順位")
C_DIFF = HEADER.index("順位変動")

# リーグ → (snapshotファイル, タブgid, events.jsonのid接尾辞)
LEAGUES = {
    "rise1": ("rise_snapshot.json", 985924559, "rise"),
    "rise2": ("beginner_snapshot.json", 1431297116, "rise2"),
    "rise3": ("rise3_snapshot.json", 154264078, "rise3"),
}


def err(*a):
    print(*a, file=sys.stderr)


def latest_tsv():
    f = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not f:
        raise SystemExit("❌ creator_data_*.tsv が見つからない")
    return f[-1]


def load_tsv():
    """クリエイターID → 行（最新TSV）。"""
    path = latest_tsv()
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cid = (r.get("クリエイターID") or "").strip()
            if cid:
                out[cid] = r
    return out, path


def event_period(month, suffix):
    """events.json のイベント期間（サイトの表示と同じ＝データ反映日まで）。"""
    ym = month.replace("-", "")
    try:
        doc = json.load(open(os.path.join(DATA, "events.json"), encoding="utf-8"))
        for ev in doc.get("events", []):
            if ev.get("id") == f"tiktok-{ym}-{suffix}":
                return f"{ev.get('period_start','')} ~ {ev.get('period_end','')}"
    except Exception as e:
        err(f"  ⚠️ events.json から期間を取れない: {e}")
    return ""


def snapshot(fname):
    p = os.path.join(DATA, fname)
    doc = json.load(open(p, encoding="utf-8"))
    return doc.get("month", ""), (doc.get("ranks") or {})


def prev_from_git(fname):
    """状態ファイルが無い初回用。snapshotを更新した1つ前のコミットから拾う。"""
    try:
        rel = f"data/{fname}"
        log = subprocess.run(["git", "log", "--format=%H", "-n", "2", "--", rel],
                             cwd=REPO, capture_output=True, text=True, check=True)
        commits = [c for c in log.stdout.split() if c]
        if len(commits) < 2:
            return {}
        show = subprocess.run(["git", "show", f"{commits[1]}:{rel}"],
                              cwd=REPO, capture_output=True, text=True, check=True)
        doc = json.loads(show.stdout)
        ranks = doc.get("ranks") or {}
        err(f"  （前日順位は git履歴 {commits[1][:7]} から取得: {len(ranks)}名）")
        return {cid: v.get("rank") for cid, v in ranks.items()}
    except Exception as e:
        err(f"  ⚠️ git履歴から前日順位を取れない: {e}")
        return {}


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def col_a1(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def move_text(prev, rank):
    """順位変動をSlackと同じ書き方で返す（例「4位→2位（2人抜き）」）。
    前日に載っていない人は「新規掲載」、同じ順位は「変動なし」。"""
    if not prev:
        return "新規掲載"
    prev = int(prev)
    d = prev - rank
    if d > 0:
        return f"{prev}位→{rank}位（{d}人抜き）"
    if d < 0:
        return f"{prev}位→{rank}位（{-d}人に抜かれた）"
    return "変動なし"


def build_rows(league, period, tsv, prev_ranks):
    fname, _gid, _sfx = LEAGUES[league]
    _month, ranks = snapshot(fname)
    rows = []
    for cid, v in sorted(ranks.items(), key=lambda kv: kv[1].get("rank", 10 ** 9)):
        t = tsv.get(cid) or {}
        name = (t.get("ライバー名") or v.get("name") or "").strip()
        pr = prev_ranks.get(cid)
        rank = int(v.get("rank") or 0)
        rows.append([
            name,
            (t.get("バックステージリンク") or "").strip(),
            (t.get("Liny URL") or "").strip(),
            period,
            cid,                                    # 19桁なので必ず文字列のまま（RAW書き込み）
            (t.get("クリエイターのユーザー名") or "").strip(),
            rank,
            int(pr) if pr else "",                  # 新規掲載は空欄
            move_text(pr, rank),                    # Slackと同じ書き方「4位→2位（2人抜き）」
            int(v.get("pt") or 0),
        ])
    return rows, ranks


def write_sheet(gc, gid, rows, dry=False, label=""):
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    body = [[f"最終更新: {stamp} (JST)"] + [""] * (len(HEADER) - 1), HEADER] + rows
    if dry:   # dry-runではスプレッドシートに一切触らない
        print(f"  [dry-run] {label}: {len(rows)}名ぶんを書き込む予定（1行目={body[0][0]}）")
        for r in rows[:3]:
            print("    ", " | ".join(str(c) for c in [r[0]] + r[C_CID:]))
        return label
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = next((w for w in sh.worksheets() if w.id == gid), None)
    if ws is None:
        raise SystemExit(f"❌ gid={gid} のタブが無い")
    if ws.col_count < len(HEADER):
        ws.add_cols(len(HEADER) - ws.col_count)
    if ws.row_count < len(body):
        ws.add_rows(len(body) - ws.row_count)
    ws.clear()
    last = col_a1(len(HEADER))
    ws.update(range_name=f"A1:{last}{len(body)}", values=body, value_input_option="RAW")
    ws.freeze(rows=2)
    # URL列はRAWだとただの文字列でクリックできないので入れ直す（19桁IDは含まない列）
    for nm in LINK_COLS:
        i = HEADER.index(nm)
        letter = col_a1(i + 1)
        vals = [[r[i]] for r in rows]
        if vals:
            ws.update(range_name=f"{letter}3:{letter}{len(body)}", values=vals, value_input_option="USER_ENTERED")
    return ws.title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="rise1,rise2,rise3")
    ap.add_argument("--month", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    targets = [x for x in a.league.split(",") if x in LEAGUES]
    if not targets:
        raise SystemExit("❌ --league は rise1,rise2,rise3 のいずれか")

    tsv, tsv_path = load_tsv()
    print(f"📄 TSV: {os.path.basename(tsv_path)}（{len(tsv)}名）")
    state = load_state()
    gc = None if a.dry_run else gspread.authorize(
        Credentials.from_service_account_file(CREDS, scopes=SCOPES))

    for lg in targets:
        fname, gid, sfx = LEAGUES[lg]
        month = a.month or snapshot(fname)[0]
        period = event_period(month, sfx)
        st = state.get(lg) or {}
        if st.get("date") == period:        # 同じデータ期間での再実行＝前日順位は据え置き
            prev = st.get("prev_ranks") or {}
            err(f"  （{lg}: 同じデータ期間での再実行なので1世代前の順位を使う）")
        else:
            prev = st.get("ranks") or prev_from_git(fname)
        rows, ranks = build_rows(lg, period, tsv, prev)
        title = write_sheet(gc, gid, rows, dry=a.dry_run, label=lg.upper())
        miss = sum(1 for r in rows if r[C_CID] not in tsv)
        nuki = sum(1 for r in rows if "人抜き" in str(r[C_DIFF]))
        print(f"✅ {title}: {len(rows)}名（期間 {period}"
              f"・前日順位あり {sum(1 for r in rows if r[C_PREV] != '')}名・人抜き {nuki}名"
              + (f"・TSV未突合 {miss}名" if miss else "") + ")")
        if not a.dry_run and st.get("date") != period:
            # prev_ranks には「今回 前日順位として実際に使った順位」を残す。
            # こうしておけば同じデータ期間で再実行しても前日順位が消えない（初回はgit由来）。
            state[lg] = {"date": period,
                         "ranks": {cid: v.get("rank") for cid, v in ranks.items()},
                         "prev_date": st.get("date", ""),
                         "prev_ranks": prev}
    if not a.dry_run:
        state["updated"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
