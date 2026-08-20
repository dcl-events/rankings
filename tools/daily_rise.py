#!/usr/bin/env python3
"""⚡️DCL RISE⚡️（ビギナー卒業〜中間層）ランキングの日次更新＋順位差分。

daily_beginner.py と同じ構造・同じポイント式で、対象レンジだけが違う。

  point = M×10 + AH×5 + AG×1000  （M=ダイヤ, AH=Matchダイヤ, AG=Match数）

対象（どちらかを満たす）:
  A. 中間層     : 10000 <= 先月ダイヤ <= 200000
                  （＝前月10万pt以上・前月20万ダイヤ以下。※後述の近似あり）
  B. 卒業ピック : 先月ダイヤ < 10000（＝前月ビギナー該当）で、当月pt >= 100000
共通: 先月ダイヤ > 200000 は除外（上位層）。掲載は pt >= floor（既定1＝対象者は全員載せる。
      当月pt=0 の人は build.py 側がスコア0行として自動除外する）。

⚠️近似について: クリエイターデータの「先月」列はダイヤ/時間/日数/フォロワー/LIVE数のみで
LIVE Match実績が無いため、前月ポイントは 先月ダイヤ×10 で近似している
（先月ダイヤ1万 ≒ 前月10万pt）。厳密にやる場合は前月分xlsxを取得して差し替える。

使い方:
  python3 tools/daily_rise.py [--month 2026-08] [--floor 1] [--date 8/17]
"""
import sys, os, re, csv, glob, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_OUT = os.path.join(REPO, "data", "tiktok-202608-rise.csv")
SNAP = os.path.join(REPO, "data", "rise_snapshot.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
URL = "https://dcl-events.github.io/rankings/tiktok-202608-rise.html"
MENTION = "<@U0A6WU3P3LL>"   # ito_sukeaki

GRAD_PT = 100000      # ビギナー卒業ライン（当月pt）
LAST_MIN = 10000      # 中間層の下限（先月ダイヤ ≒ 前月10万pt）
LAST_MAX = 200000     # 中間層の上限（先月20万ダイヤ）

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
    month = "2026-08"; floor = 1; date = ""; dry = False; bare = False
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--floor": floor = int(args[i+1]); i += 2
        elif args[i] == "--date": date = args[i+1]; i += 2
        elif args[i] == "--dry-run": dry = True; i += 1
        elif args[i] == "--bare": bare = True; i += 1
        else: i += 1

    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        err("TSVなし:", TSV_DIR); sys.exit(1)
    tsv = cands[-1]
    err("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    ID = c["クリエイターID"]; N = c["ライバー名"]; D = c["ダイヤモンド"]
    L = c["LIVE時間"]; LAST = c["先月のダイヤモンド数"]; DAYS = c["有効LIVE日数"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]

    rise = []
    for r in rows[1:]:
        if len(r) <= max(ID, N, D, L, LAST, AG, AH): continue
        cur = toint(r[D]); ah = toint(r[AH]); ag = toint(r[AG])
        last_i = toint(r[LAST])
        if last_i > LAST_MAX: continue          # 上位層は対象外
        pt = cur * 10 + ah * 5 + ag * 1000
        mid  = LAST_MIN <= last_i <= LAST_MAX   # 前月10万pt以上（近似）
        grad = last_i < LAST_MIN and pt >= GRAD_PT   # ビギナー卒業ピック
        if not (mid or grad): continue
        if pt < floor: continue
        rise.append({"cid": str(r[ID]).strip(), "name": r[N].strip(), "pt": pt,
                     "cur": cur, "ag": ag, "live": hm(r[L]), "days": toint(r[DAYS]),
                     "route": "卒業" if grad else "中間層"})
    rise.sort(key=lambda x: -x["pt"])

    # CSV書き出し（ビギナーと同じ3列）
    if dry:
        err(f"[dry-run] CSV未更新（掲載 {len(rise)}名の想定）")
    else:
        with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["name", "point", "livetime", "days"])
            for b in rise:
                w.writerow([b["name"], b["pt"], b["live"], b["days"]])
    err(f"CSV {len(rise)}名 (中間層 {sum(1 for b in rise if b['route']=='中間層')} / "
        f"卒業 {sum(1 for b in rise if b['route']=='卒業')})")

    # 前回スナップショットと比較（cid基準）
    prev = {}
    if os.path.exists(SNAP):
        try: prev = json.load(open(SNAP))
        except Exception: prev = {}
    climbers = []
    newcomers = []
    for i, b in enumerate(rise):
        r = i + 1; pv = prev.get(b["cid"]) if prev else None
        if prev and not pv:
            newcomers.append((b["name"], r, b["route"]))
        elif pv and r < pv.get("rank", 0):
            climbers.append((b["name"], pv["rank"], r, pv["rank"] - r))
    climbers.sort(key=lambda x: x[2])
    newcomers.sort(key=lambda x: x[1])

    # Slackメッセージ
    if bare:
        msg = ["⚡️DCL RISE⚡️", URL, ""]
    else:
        head = f"⚡️DCL RISE⚡️ 更新（{date}時点）" if date else "⚡️DCL RISE⚡️ 更新"
        msg = [head, MENTION, URL, ""]
    if not prev:
        msg.append("（初回更新。順位変動の比較は次回から）")
    else:
        if climbers:
            msg.append("📈 上のランクを抜いた人")
            for name, pr, nr, n in climbers:
                msg.append(f"・{name}：{pr}位→{nr}位（{n}人抜き）")
        else:
            msg.append("📊 上位を抜いた人はいませんでした（順位変動なし）")
        if newcomers:
            msg.append("")
            msg.append("🆙 新しくRISE入り")
            for name, r, route in newcomers:
                tag = "ビギナー卒業" if route == "卒業" else "中間層"
                msg.append(f"・{name}：{r}位（{tag}）")
    print("\n".join(msg))

    # スナップショット更新
    if dry:
        err("[dry-run] snapshotは未更新"); return
    json.dump({b["cid"]: {"rank": i + 1, "name": b["name"], "pt": b["pt"]}
               for i, b in enumerate(rise)},
              open(SNAP, "w"), ensure_ascii=False, indent=0)
    err("snapshot updated")

if __name__ == "__main__":
    main()
