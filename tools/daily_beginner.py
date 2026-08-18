#!/usr/bin/env python3
"""DCLビギナーランキングの日次更新＋順位差分。

- 最新 out/creator_data_*.tsv を読む（新規DLなし・全員・実名）
- ビギナー抽出＋新ポイント式＋floorで CSV を生成
- 前回スナップショット(data/beginner_snapshot.json, クリエイターID基準)と比較し
  「上のランクを抜いた人」= 順位が上がった人 を算出
- スナップショットを更新
- Slack投稿用メッセージを標準出力に出す（診断は標準エラーへ）

point = M×10 + AH×5 + AG×1000  （M=ダイヤ, AH=Matchダイヤ, AG=Match数）
対象 = (先月ダイヤ<10000 or 入会が対象月) かつ 当月ダイヤ>=1、掲載= pt>=floor

使い方:
  python3 tools/daily_beginner.py [--month 2026-08] [--floor 1000] [--date 8/17]
"""
import sys, os, re, csv, glob, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_OUT = os.path.join(REPO, "data", "tiktok-202608-newcomer.csv")
SNAP = os.path.join(REPO, "data", "beginner_snapshot.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
URL = "https://dcl-events.github.io/rankings/tiktok-202608-newcomer.html"
MENTION = "<@U0A6WU3P3LL>"   # ito_sukeaki

def err(*a): print(*a, file=sys.stderr)
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
    month = "2026-08"; floor = 1000; date = ""
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--floor": floor = int(args[i+1]); i += 2
        elif args[i] == "--date": date = args[i+1]; i += 2
        else: i += 1

    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        err("TSVなし:", TSV_DIR); sys.exit(1)
    tsv = cands[-1]
    err("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    ID = c["クリエイターID"]; N = c["ライバー名"]; J = c["入会日"]; D = c["ダイヤモンド"]
    L = c["LIVE時間"]; LAST = c["先月のダイヤモンド数"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]

    beg = []
    for r in rows[1:]:
        if len(r) <= max(ID, N, J, D, L, LAST, AG, AH): continue
        cur = toint(r[D]); ah = toint(r[AH]); ag = toint(r[AG])
        last_raw = r[LAST].strip(); last_i = toint(last_raw)
        join = r[J][:10]; is_new = join.startswith(month)
        if cur < 1: continue
        if not ((last_i < 10000) or is_new): continue
        pt = cur * 10 + ah * 5 + ag * 1000
        if pt < floor: continue
        beg.append({"cid": str(r[ID]).strip(), "name": r[N].strip(), "pt": pt,
                    "cur": cur, "ag": ag, "live": hm(r[L])})
    beg.sort(key=lambda x: -x["pt"])

    # CSV書き出し
    with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["name", "point", "livetime"])
        for b in beg:
            w.writerow([b["name"], b["pt"], b["live"]])
    err(f"CSV {len(beg)}名")

    # 前回スナップショットと比較（cid基準）
    prev = {}
    if os.path.exists(SNAP):
        try: prev = json.load(open(SNAP))
        except Exception: prev = {}
    new_rank = {b["cid"]: i + 1 for i, b in enumerate(beg)}
    climbers = []
    for i, b in enumerate(beg):
        r = i + 1; pr = prev.get(b["cid"], {}).get("rank") if prev else None
        if pr and r < pr:
            climbers.append((b["name"], pr, r, pr - r))
    climbers.sort(key=lambda x: x[2])

    # Slackメッセージ
    head = f"🌱 DCLビギナーランキング 更新（{date}時点）" if date else "🌱 DCLビギナーランキング 更新"
    msg = [head, MENTION, URL, ""]
    if not prev:
        msg.append("（初回更新。順位変動の比較は次回から）")
    elif climbers:
        msg.append("📈 上のランクを抜いた人")
        for name, pr, nr, n in climbers:
            msg.append(f"・{name}：{pr}位→{nr}位（{n}人抜き）")
    else:
        msg.append("📊 上位を抜いた人はいませんでした（順位変動なし）")
    print("\n".join(msg))

    # スナップショット更新
    json.dump({b["cid"]: {"rank": i + 1, "name": b["name"], "pt": b["pt"]}
               for i, b in enumerate(beg)},
              open(SNAP, "w"), ensure_ascii=False, indent=0)
    err("snapshot updated")

if __name__ == "__main__":
    main()
