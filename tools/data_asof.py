#!/usr/bin/env python3
"""最新 creator_data_*.tsv から「データ期間の末日」を導出する。

Backstageのクリエイターデータは DL日の2日前まで しか反映されない（実測）:
  8/18 DL → 皆勤ライバーの有効LIVE日数 16日（= 8/1〜8/16）
  8/19 DL → 17日（= 8/1〜8/17）
  8/20 DL → 18日（= 8/1〜8/18）
いずれも「DL日 − 2日」と一致した。

実行時刻(クロック)ではなく、実際に読むTSVのファイル日付を基準にするので、
当日のDLが失敗して前日以前のTSVを使った場合もラベルが実データとズレない。

使い方:
  python3 tools/data_asof.py                      # 2026-08-18
  python3 tools/data_asof.py --fmt md             # 8/18
  python3 tools/data_asof.py --set-events ID,ID   # events.json の period_end を更新
"""
import sys, os, re, glob, json
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(REPO, "data", "events.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
LAG_DAYS = 2   # Backstageの反映遅れ（DL日 − 2日 までのデータ）


def data_end():
    """最新TSVのファイル日付 − LAG_DAYS を date で返す。"""
    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        sys.exit("creator_data_*.tsv が見つかりません")
    base = os.path.basename(cands[-1])
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", base)
    if not m:
        sys.exit(f"TSV名から日付を読めません: {base}")
    dl = datetime(int(m[1]), int(m[2]), int(m[3])).date()
    return dl - timedelta(days=LAG_DAYS), base


def set_events(ids, end):
    with open(EVENTS, encoding="utf-8") as fh:
        doc = json.load(fh)
    changed = []
    for ev in doc["events"]:
        if ev.get("id") in ids and ev.get("period_end") != end.isoformat():
            changed.append(f'{ev["id"]}: {ev.get("period_end")} → {end.isoformat()}')
            ev["period_end"] = end.isoformat()
    if changed:
        with open(EVENTS, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return changed


def main():
    args = sys.argv[1:]
    fmt, ids = "iso", None
    i = 0
    while i < len(args):
        if args[i] == "--fmt":
            fmt = args[i + 1]; i += 2
        elif args[i] == "--set-events":
            ids = set(args[i + 1].split(",")); i += 2
        else:
            sys.exit(f"unknown arg: {args[i]}")
    end, base = data_end()
    print(f"source: {base} → データ期間末 {end.isoformat()}", file=sys.stderr)
    if ids:
        for line in set_events(ids, end) or ["period_end 変更なし"]:
            print(line, file=sys.stderr)
    print(end.strftime("%-m/%d") if fmt == "md" else end.isoformat())


if __name__ == "__main__":
    main()
