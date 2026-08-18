#!/usr/bin/env python3
"""DCLビギナーランキング用CSVを、日次ルーティンの out/creator_data_*.tsv から生成する。

このTSVは ~/Claude/tiktok-automation/run-daily.sh が毎朝生成し、スプシ
「クリエイターデータ_Claude」(gid=1208970074) に流し込んでいるのと同一中身。
ローカルファイルなので新規DL不要・全241名フル・ライバー名は本物の絵文字付き
（Drive経由だと幅広タブが40行で切れる/絵文字が文字化けする問題を回避）。

ビギナー仕様:
  対象 = (先月ダイヤ < 10000 または 入会が対象月) かつ 当月ダイヤ >= 1
  掲載 = ポイント >= FLOOR(=1000)
ポイント:
  point = M×10 + AH×5 + AG×1000
    M=ダイヤモンド, AH=LIVE Matchで獲得したダイヤモンド数, AG=LIVE Match数
    （通常10pt/個、バトルダイヤは15pt/個＝差分+5、1バトル1000pt）

使い方:
  python3 tools/beginner_from_tsv.py [--tsv <path>] [--month 2026-08] [--floor 500]
  --tsv 省略時は ~/Claude/tiktok-automation/out/creator_data_*.tsv の最新を使う。
"""
import sys, os, re, csv, glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "tiktok-202608-newcomer.csv")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")

def toint(v):
    if v in (None, "-", ""): return 0
    v = str(v).replace(",", "").strip()
    try: return int(float(v))
    except ValueError: return 0

def hm(v):
    s = str(v); h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s)
    if h or m: return f"{int(h.group(1)) if h else 0}h{int(m.group(1)) if m else 0}m"
    return ""

def main():
    args = sys.argv[1:]
    tsv = None; month = "2026-08"; floor = 1000
    i = 0
    while i < len(args):
        if args[i] == "--tsv": tsv = args[i+1]; i += 2
        elif args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--floor": floor = int(args[i+1]); i += 2
        else: i += 1
    if not tsv:
        cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
        if not cands:
            sys.exit("TSVが見つかりません: " + TSV_DIR)
        tsv = cands[-1]
    print("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    N = c["ライバー名"]; J = c["入会日"]; D = c["ダイヤモンド"]
    L = c["LIVE時間"]; LAST = c["先月のダイヤモンド数"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]

    beg = []
    for r in rows[1:]:
        if len(r) <= max(N, J, D, L, LAST, AG, AH): continue
        name = r[N].strip()
        cur = toint(r[D]); ah = toint(r[AH]); ag = toint(r[AG])
        last_raw = r[LAST].strip()
        last_new = last_raw in ("", "-")
        last_i = toint(last_raw)
        join = r[J][:10]; is_new = join.startswith(month)
        if cur < 1: continue
        if not ((last_i < 10000) or is_new): continue
        pt = cur * 10 + ah * 5 + ag * 1000
        if pt < floor: continue
        beg.append({"name": name, "pt": pt, "cur": cur, "ag": ag, "ah": ah,
                    "live": hm(r[L])})
    beg.sort(key=lambda x: -x["pt"])
    print(f"ビギナー({floor}pt+) {len(beg)}名\n")
    for k, b in enumerate(beg, 1):
        grad = "🎓" if b["cur"] >= 10000 else ""
        print(f'{k:>2} {b["name"]:<26}{b["pt"]:>10,}pt (ダイヤ{b["cur"]:,}/戦{b["ag"]}) {b["live"]:<7}{grad}')

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["name", "point", "livetime"])
        for b in beg:
            w.writerow([b["name"], b["pt"], b["live"]])
    print("\nwrote", os.path.relpath(OUT, REPO), ":", len(beg), "rows")

if __name__ == "__main__":
    main()
