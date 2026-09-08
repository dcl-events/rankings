#!/usr/bin/env python3
"""前月の獲得ポイント(cid→pt)を、その月の最終TSVから算出して
   data/prev_month_points_<YYYYMM>.json に保存する。

ビギナー参加判定の「前月ポイント<30万」で使う。TSVには先月のMatch数/ファン等が
無いため、前月ぶんは前月の実TSVから当月指標として計算しておく必要がある。
式は daily_beginner.py と厳密一致（M×10 + AH×5 + AG×1000 + 継続 + ファン）。

使い方:  python3 tools/build_prev_month_points.py --month 2026-08
  → data/prev_month_points_202608.json を生成（期間が2026-08の最新TSVを使用）
"""
import sys, os, re, csv, json, glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
BONUS_PT, BONUS_DAYS, BONUS_HOURS, FAN_CAP = 50000, 18, 70, 200

def toint(v):
    if v in (None, "-", ""): return 0
    v = str(v).replace(",", "").strip()
    try: return int(float(v))
    except ValueError: return 0
def live_hours(v):
    s = str(v); h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s); sec = re.search(r"(\d+)秒", s)
    return (int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0)/60 + (int(sec.group(1)) if sec else 0)/3600
def calc_pt(M, AH, AG, days, live_raw, fans):
    base = M*10 + AH*5 + AG*1000 + (BONUS_PT if (days >= BONUS_DAYS and live_hours(live_raw) >= BONUS_HOURS) else 0)
    return base + base * (min(fans, FAN_CAP)//10) // 100

def main():
    month = None
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == "--month": month = a[i+1]
    if not month:
        sys.exit("usage: --month YYYY-MM")
    period = month + "-01"          # データ期間の先頭 '2026-08-01'
    cands = []
    for f in sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv"))):
        with open(f, encoding="utf-8") as fh:
            fh.readline()                     # ヘッダ
            row2 = fh.readline().split("\t")   # 先頭データ行
        dperiod = row2[2] if len(row2) > 2 else ""
        if dperiod.startswith(period):
            cands.append(f)
    if not cands:
        sys.exit(f"期間 {period} のTSVが見つかりません")
    tsv = cands[-1]                            # その月の最終（最新）TSV
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    c = {n: i for i, n in enumerate(rows[0])}
    out = {}
    for r in rows[1:]:
        cid = r[c["クリエイターID"]].strip()
        if not cid: continue
        out[cid] = calc_pt(toint(r[c["ダイヤモンド"]]), toint(r[c["LIVE Matchで獲得したダイヤモンド数"]]),
                           toint(r[c["LIVE Match数"]]), toint(r[c["有効LIVE日数"]]),
                           r[c["LIVE時間"]], toint(r[c["ファンクラブのアクティブなファン"]]))
    dst = os.path.join(REPO, "data", f"prev_month_points_{month.replace('-','')}.json")
    json.dump(out, open(dst, "w"), ensure_ascii=False)
    print(f"source: {os.path.basename(tsv)}  →  {os.path.relpath(dst, REPO)} ({len(out)}名)")

if __name__ == "__main__":
    main()
