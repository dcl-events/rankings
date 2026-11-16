#!/usr/bin/env python3
"""毎朝のランキング通知（スレッド返信）の本文を組み立てる。

2026-11-16に池さんの指示で中身を変更：
  × 細かい順位アップ（◯人抜きの一覧）→ スプレッドシートで見てもらう
  ○ RISEの昇格（＝各リーグのクリア）・RISE1卒業・RISE3の新規参加・スプシ3枚のURL

読むのは日次スクリプトが書いた記録だけ（順番は daily_rise3/beginner/rise → これ）:
  data/rise3_cleared.json      RISE3クリア → ⚡️DCL RISE2⚡️へ
  data/beginner_graduated.json RISE2クリア → ⚡️DCL RISE1⚡️へ
  data/rise_milestone.json     RISE1クリア → RISE卒業
  data/debut_records.json      RISE3に初めて載った人（初配信30日以内のデビュー組だけ）
ptは各リーグの snapshot から、ユーザー名は記録→最新TSVの順で引く。

使い方: python3 tools/slack_notice.py [--date 2026-11-16] [--month 2026-11]
"""
import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import debut  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
JST = timezone(timedelta(hours=9))
SHEET = "https://docs.google.com/spreadsheets/d/1A-WSX4mteR-E5kY8V82dTUqoTcD0GDLA0Uq0qiDTzh4/edit?gid={gid}#gid={gid}"
SHEET_GIDS = (("RISE1", 985924559), ("RISE2", 1431297116), ("RISE3", 154264078))

# (記録ファイル, snapshot, 見出し)
CLEAR_SRC = [
    ("rise3_cleared.json", "rise3_snapshot.json", "RISE3クリア（20万pt）→ ⚡️DCL RISE2⚡️へ"),
    ("beginner_graduated.json", "beginner_snapshot.json", "RISE2クリア（200万pt）→ ⚡️DCL RISE1⚡️へ"),
    ("rise_milestone.json", "rise_snapshot.json", "RISE1クリア（400万pt）→ RISE卒業"),
]
DATE_KEYS = ("cleared_on", "graduated_on", "achieved_on")


def jload(name, default=None):
    try:
        return json.load(open(os.path.join(DATA, name), encoding="utf-8")) or (default or {})
    except Exception:
        return default or {}


def tsv_users():
    """クリエイターID → ユーザー名（最新TSV）。記録にuserが無い月の保険。"""
    files = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    out = {}
    if not files:
        return out
    with open(files[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cid = (r.get("クリエイターID") or "").strip()
            if cid:
                out[cid] = (r.get("クリエイターのユーザー名") or "").strip()
    return out


def handle(cid, rec, users):
    u = str(rec.get("user") or "").strip() or users.get(str(cid), "")
    return f"｜@{u}" if u else ""


def clears_today(today, month, users):
    """その日クリアした人を [(見出し, [行...])] で返す。"""
    out = []
    for fname, snap, label in CLEAR_SRC:
        doc = jload(fname)
        if month and doc.get("month") and doc["month"] != month:
            out.append((label, []))          # 別月の記録は使わない
            continue
        pts = {cid: v.get("pt") for cid, v in (jload(snap).get("ranks") or {}).items()}
        lines = []
        for cid, v in (doc.get("livers") or {}).items():
            d = next((v.get(k) for k in DATE_KEYS if v.get(k)), "")
            if d != today:
                continue
            pt = pts.get(cid)
            pt_s = f"：{int(pt):,}pt" if pt else ""
            lines.append(f"　・{v.get('name', '')}{handle(cid, v, users)}{pt_s}")
        out.append((label, lines))
    return out


def debuts_today(today, users):
    """その日RISE3に初めて載ったデビュー組（初配信30日以内）の行。"""
    recs = (debut.load().get("leagues") or {}).get("rise3") or {}
    newly = [(cid, r) for cid, r in recs.items() if r.get("date") == today]
    keep, unknown = debut.filter_new_debuts(newly)
    if unknown:
        print("初配信日が未登録で判定できなかった新規: "
              + " / ".join(r.get("name", "") for _c, r in unknown), file=sys.stderr)
    keep.sort(key=lambda kv: kv[1].get("rank") or 10 ** 9)
    return debut.slack_lines(keep, uh=lambda cid: handle(cid, recs.get(cid, {}), users),
                             label="🆕 RISE3 新規参加")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="記録の基準日（既定=今日 JST）")
    ap.add_argument("--month", default="", help="対象月 YYYY-MM（既定=snapshotの月）")
    a = ap.parse_args()
    today = a.date or datetime.now(JST).strftime("%Y-%m-%d")
    month = a.month or (jload("rise3_snapshot.json").get("month") or "")
    users = tsv_users()

    msg = ["🎓 本日の昇格・卒業"]
    blocks = clears_today(today, month, users)
    if any(lines for _l, lines in blocks):
        for label, lines in blocks:
            msg.append(f"・{label}" + ("" if lines else "：なし"))
            msg += lines
    else:
        msg.append("・本日の昇格・卒業はありません")

    msg += debuts_today(today, users)

    msg.append("")
    msg.append("📄 順位の詳細（当日順位・前日順位・◯人抜き）はスプレッドシートで確認")
    for name, gid in SHEET_GIDS:
        msg.append(f"{name} {SHEET.format(gid=gid)}")
    print("\n".join(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
