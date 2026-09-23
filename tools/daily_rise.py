#!/usr/bin/env python3
"""⚡️DCL RISE⚡️（ビギナー卒業〜中間層）ランキングの日次更新＋順位差分。

daily_beginner.py と同じ構造・同じポイント式で、対象レンジだけが違う。

  point = M×10 + AH×5 + AG×1000  （M=ダイヤ, AH=Matchダイヤ, AG=Match数）

対象（どちらかを満たす）:
  A. 中間層     : 30000 <= 先月ダイヤ <= 200000
                  （＝前月30万pt以上・前月20万ダイヤ以下。※後述の近似あり）
  B. 卒業ピック : 先月ダイヤ < 30000 で、当月pt >= 300000（ビギナー卒業ラインと同値）
共通: 先月ダイヤ > 200000 は除外（上位層）。掲載は pt >= floor（既定1＝対象者は全員載せる。
      当月pt=0 の人は build.py 側がスコア0行として自動除外する）。

⚠️近似について: クリエイターデータの「先月」列はダイヤ/時間/日数/フォロワー/LIVE数のみで
LIVE Match実績が無いため、前月ポイントは 先月ダイヤ×10 で近似している
（先月ダイヤ3万 ≒ 前月30万pt）。厳密にやる場合は前月分xlsxを取得して差し替える。

使い方:
  python3 tools/daily_rise.py [--month 2026-09] [--floor 1] [--date 8/17]
"""
import sys, os, re, csv, glob, json
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "data", "rise_snapshot.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
MENTION = "<@U0A6WU3P3LL>"   # ito_sukeaki
JST = timezone(timedelta(hours=9))

GRAD_PT = 300000      # ビギナー卒業ライン（当月pt）
LAST_MIN = 30000      # 中間層の下限（先月ダイヤ ≒ 前月30万pt）
LAST_MAX = 200000     # 中間層の上限（先月20万ダイヤ）

BONUS_PT = 50000    # 継続ボーナス
BONUS_DAYS = 18     # 有効LIVE日数（月間）
BONUS_HOURS = 70    # LIVE時間（月間・時間）
FAN_CAP = 200       # ファンクラブボーナスの計算上限人数（10人ごとに+1%＝最大+20%）

def paths_for(month):
    """対象月(YYYY-MM)から CSV出力先・公開URL を作る（月替わりで自動的に当月へ切り替わる）。"""
    ym = month.replace("-", "")
    return (os.path.join(REPO, "data", f"tiktok-{ym}-rise.csv"),
            f"https://dcl-events.github.io/rankings/tiktok-{ym}-rise.html")

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

def live_hours(v):
    """「60時間 4分 35秒」→ 60.07（時間）。月間LIVE時間の判定に使う。"""
    s = str(v)
    h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s); sec = re.search(r"(\d+)秒", s)
    return (int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0) / 60 \
           + (int(sec.group(1)) if sec else 0) / 3600

def keizoku_bonus(days, live_raw):
    """継続ボーナス：有効LIVE日数18日以上 かつ 月間LIVE時間70時間以上 で 50,000pt。"""
    return BONUS_PT if (days >= BONUS_DAYS and live_hours(live_raw) >= BONUS_HOURS) else 0

def fan_bonus(fans, base_pt):
    """ファンクラブボーナス：アクティブファン10人ごとに合計ポイント+1%（上限200人＝+20%）。
    戻り値 (加算率%, 加算pt)。端数は切り捨て。"""
    pct = min(fans, FAN_CAP) // 10
    return pct, base_pt * pct // 100

def main():
    args = sys.argv[1:]
    # 既定の対象月 = 「today − 2日」が属する月（Backstageの2日遅れに自動追従）。
    # 通常は run-daily-tiktok-rankings.sh が実TSVから求めた --month で上書きされる。
    month = (datetime.now(JST) - timedelta(days=2)).strftime("%Y-%m")
    floor = 1; date = ""; dry = False; bare = False
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--floor": floor = int(args[i+1]); i += 2
        elif args[i] == "--date": date = args[i+1]; i += 2
        elif args[i] == "--dry-run": dry = True; i += 1
        elif args[i] == "--bare": bare = True; i += 1
        else: i += 1
    CSV_OUT, URL = paths_for(month)
    today = datetime.now(JST).strftime("%Y-%m-%d")

    # RISE達成フラグ：当月「base＋stampの合算」が MILESTONE_PT(300万) 到達で「◯/◯ 300万pt達成！」を記録。
    MILESTONE_PT = 3000000
    MSTONE = os.path.join(REPO, "data", "rise_milestone.json")
    mstate = {"month": month, "livers": {}}
    if os.path.exists(MSTONE):
        try:
            _m = json.load(open(MSTONE))
            if _m.get("month") == month: mstate = _m
        except Exception: pass
    mlivers = mstate["livers"]

    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        err("TSVなし:", TSV_DIR); sys.exit(1)
    tsv = cands[-1]
    err("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    ID = c["クリエイターID"]; N = c["ライバー名"]; D = c["ダイヤモンド"]
    L = c["LIVE時間"]; LAST = c["先月のダイヤモンド数"]; DAYS = c["有効LIVE日数"]; FANS = c["ファンクラブのアクティブなファン"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]

    # スタンプラリー獲得pt（tier=rise）。卒業ピックの30万判定を base＋stamp の合算で行う。
    STAMPF = os.path.join(REPO, "data", "stamp_points.json")
    stamp_r = {}
    if os.path.exists(STAMPF):
        try:
            stamp_r = {k: int((v or {}).get("rise", 0) or 0)
                       for k, v in (json.load(open(STAMPF)).get("pts") or {}).items()}
        except Exception: stamp_r = {}
    # ビギナー卒業者(=beginner_graduated.json、当月)は確実にRISEへ引き継ぐ（スタンプはtier別で
    # 差があり得るため、卒業判定はビギナー側の記録を正とする）。
    grad_set = set()
    GF = os.path.join(REPO, "data", "beginner_graduated.json")
    if os.path.exists(GF):
        try:
            _g = json.load(open(GF))
            if _g.get("month") == month: grad_set = set((_g.get("livers") or {}).keys())
        except Exception: grad_set = set()

    rise = []
    for r in rows[1:]:
        if len(r) <= max(ID, N, D, L, LAST, AG, AH): continue
        if not str(r[ID]).strip().isdigit(): continue   # 退会ライバー（IDが「…退会しました」等）は除外
        cur = toint(r[D]); ah = toint(r[AH]); ag = toint(r[AG])
        last_i = toint(r[LAST])
        if last_i > LAST_MAX: continue          # 上位層は対象外
        days = toint(r[DAYS]); bonus = keizoku_bonus(days, r[L])
        base = cur * 10 + ah * 5 + ag * 1000 + bonus
        fans = toint(r[FANS]); fanpct, fanbonus = fan_bonus(fans, base)
        pt = base + fanbonus
        rid = str(r[ID]).strip()
        tot = pt + stamp_r.get(rid, 0)          # 合算ポイント（卒業ピック判定用）
        mid  = LAST_MIN <= last_i <= LAST_MAX   # 前月10万pt以上（近似）
        # ビギナー卒業ピック：正はビギナー卒業記録。無い環境向けに合算ptのフォールバックも残す。
        grad = (rid in grad_set) or (last_i < LAST_MIN and tot >= GRAD_PT)
        if not (mid or grad): continue
        if pt < floor: continue
        # RISE達成フラグ：合算300万pt到達を初回検知日で記録（達成日は固定）
        if tot >= MILESTONE_PT and rid not in mlivers:
            mlivers[rid] = {"name": r[N].strip(), "achieved_on": today,
                            "achieved_md": f"{int(today[5:7])}/{int(today[8:10])}"}
        rise.append({"cid": str(r[ID]).strip(), "name": r[N].strip(), "pt": pt, "tot": tot,
                     "cur": cur, "ag": ag, "live": hm(r[L]), "days": days, "fans": fans, "bonus": bonus, "fanpct": fanpct, "fanbonus": fanbonus,
                     "route": "卒業" if grad else "中間層"})
    # スタンプ合算後(tot)で並べる＝web表示(build.pyの合算後ソート)と順位を一致させる
    rise.sort(key=lambda x: -x["tot"])

    # CSV書き出し（ビギナーと同じ3列）
    if dry:
        err(f"[dry-run] CSV未更新（掲載 {len(rise)}名の想定）")
    else:
        with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["name", "point", "livetime", "days", "fans", "bonus", "fanpct", "fanbonus"])
            for b in rise:
                w.writerow([b["name"], b["pt"], b["live"], b["days"], b["fans"], b["bonus"],
                            b["fanpct"], b["fanbonus"]])
    err(f"CSV {len(rise)}名 (中間層 {sum(1 for b in rise if b['route']=='中間層')} / "
        f"卒業 {sum(1 for b in rise if b['route']=='卒業')})")

    # 前回スナップショットと比較（cid基準）
    prev = {}
    if os.path.exists(SNAP):
        try:
            snap = json.load(open(SNAP))
            # {"month": YYYY-MM, "ranks": {...}}。月が変わった初日は比較しない（＝初回更新扱い）
            if snap.get("month") == month: prev = snap.get("ranks", {})
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
    json.dump({"month": month,
               "ranks": {b["cid"]: {"rank": i + 1, "name": b["name"], "pt": b["pt"]}
                         for i, b in enumerate(rise)}},
              open(SNAP, "w"), ensure_ascii=False, indent=0)
    mstate["month"] = month; mstate["livers"] = mlivers
    json.dump(mstate, open(MSTONE, "w"), ensure_ascii=False, indent=1)
    err("snapshot / 達成フラグ updated")

if __name__ == "__main__":
    main()
