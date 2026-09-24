#!/usr/bin/env python3
"""DCLビギナーランキングの日次更新＋順位差分。

- 最新 out/creator_data_*.tsv を読む（新規DLなし・全員・実名）
- ビギナー抽出＋新ポイント式＋floorで CSV を生成
- 前回スナップショット(data/beginner_snapshot.json, クリエイターID基準)と比較し
  「上のランクを抜いた人」= 順位が上がった人 を算出
- スナップショットを更新
- 当月pt>=10万に達した人は「⚡️DCL RISE⚡️へ卒業」扱い。卒業検知日から
  GRACE_DAYS 日間は猶予でビギナーにも残し、猶予明けに自動で掲載終了する
  （状態は data/beginner_graduated.json。月が変わればリセット）
- Slack投稿用メッセージを標準出力に出す（診断は標準エラーへ）

point = M×10 + AH×5 + AG×1000  （M=ダイヤ, AH=Matchダイヤ, AG=Match数）
対象 = (先月ダイヤ<10000 or 入会が対象月) かつ 当月ダイヤ>=1、掲載= pt>=floor

使い方:
  python3 tools/daily_beginner.py [--month 2026-09] [--floor 1000] [--date 8/17]
                                  [--asof 2026-08-25] [--dry-run]
  --asof   : 猶予判定の基準日を上書き（既定=今日JST）。将来日で挙動を検証できる
  --dry-run: CSV・スナップショット・卒業状態を書かずにSlack本文だけ出す
"""
import sys, os, re, csv, glob, json
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "data", "beginner_snapshot.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
MENTION = "<@U0A6WU3P3LL>"   # ito_sukeaki
GRAD = os.path.join(REPO, "data", "beginner_graduated.json")
GRAD_PT = 300000    # この当月ptに達したらビギナー卒業（⚡️DCL RISE⚡️の対象）
GRACE_DAYS = 1      # 卒業検知日からこの日数だけビギナーにも残す猶予（1=検知日のみ表示・翌日に掲載終了）
JST = timezone(timedelta(hours=9))

BONUS_PT = 50000    # 継続ボーナス
BONUS_DAYS = 18     # 有効LIVE日数（月間）
BONUS_HOURS = 70    # LIVE時間（月間・時間）
FAN_CAP = 200       # ファンクラブボーナスの計算上限人数（10人ごとに+1%＝最大+20%）

def paths_for(month):
    """対象月(YYYY-MM)から CSV出力先・公開URL を作る（月替わりで自動的に当月へ切り替わる）。"""
    ym = month.replace("-", "")
    return (os.path.join(REPO, "data", f"tiktok-{ym}-newcomer.csv"),
            f"https://dcl-events.github.io/rankings/tiktok-{ym}-newcomer.html",
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
    floor = 1000; date = ""; asof = ""; dry = False; bare = False
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--floor": floor = int(args[i+1]); i += 2
        elif args[i] == "--date": date = args[i+1]; i += 2
        elif args[i] == "--asof": asof = args[i+1]; i += 2
        elif args[i] == "--dry-run": dry = True; i += 1
        elif args[i] == "--bare": bare = True; i += 1
        else: i += 1
    today = asof or datetime.now(JST).strftime("%Y-%m-%d")
    CSV_OUT, URL, RISE_URL = paths_for(month)

    # 卒業状態（月が変わったらリセット）
    gstate = {"month": month, "livers": {}}
    if os.path.exists(GRAD):
        try:
            loaded = json.load(open(GRAD))
            if loaded.get("month") == month: gstate = loaded
        except Exception: pass
    glivers = gstate["livers"]

    # 参加判定：前月ポイント<30万（前月最終TSVから事前生成した prev_month_points_<前月>.json）。
    # ＝参加上限を卒業ライン(30万)と同じに揃える。未生成なら旧ルール(先月ダイヤ<1万)へフォールバック。
    PART_PT = GRAD_PT
    prevmonth = (datetime.strptime(month + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m")
    PREVPT = os.path.join(REPO, "data", f"prev_month_points_{prevmonth}.json")
    prev_pt = {}
    if os.path.exists(PREVPT):
        try: prev_pt = json.load(open(PREVPT))
        except Exception: prev_pt = {}
    # 前回ビギナー掲載者(cid集合)。既に当月30万超で"初登場"＝RISE勢を卒業猶予の対象から外すのに使う。
    prev_beg = set()
    if os.path.exists(SNAP):
        try:
            _s = json.load(open(SNAP))
            if _s.get("month") == month: prev_beg = set(_s.get("ranks", {}).keys())
        except Exception: pass

    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        err("TSVなし:", TSV_DIR); sys.exit(1)
    tsv = cands[-1]
    err("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    ID = c["クリエイターID"]; N = c["ライバー名"]; J = c["入会日"]; D = c["ダイヤモンド"]
    L = c["LIVE時間"]; LAST = c["先月のダイヤモンド数"]; DAYS = c["有効LIVE日数"]; FANS = c["ファンクラブのアクティブなファン"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]

    # スタンプラリー獲得pt（tier=beginner）。卒業ライン30万は base＋stamp の合算で判定する。
    STAMPF = os.path.join(REPO, "data", "stamp_points.json")
    stamp_b = {}
    if os.path.exists(STAMPF):
        try:
            stamp_b = {k: int((v or {}).get("beginner", 0) or 0)
                       for k, v in (json.load(open(STAMPF)).get("pts") or {}).items()}
        except Exception: stamp_b = {}

    beg = []; newgrads = []; dropped = []
    for r in rows[1:]:
        if len(r) <= max(ID, N, J, D, L, LAST, AG, AH): continue
        cur = toint(r[D]); ah = toint(r[AH]); ag = toint(r[AG])
        last_raw = r[LAST].strip(); last_i = toint(last_raw)
        join = r[J][:10]; is_new = join.startswith(month)
        cid = str(r[ID]).strip()
        if not cid.isdigit(): continue   # 退会ライバー（IDが「クリエイターがエージェンシーを退会しました」等）は除外
        if cur < 1: continue
        # 参加判定：前月ポイント<30万 or 当月デビュー（前月pt未生成時は先月ダイヤ<1万にフォールバック）
        if prev_pt:
            if not ((prev_pt.get(cid, 0) < PART_PT) or is_new): continue
        else:
            if not ((last_i < 10000) or is_new): continue
        days = toint(r[DAYS]); bonus = keizoku_bonus(days, r[L])
        base = cur * 10 + ah * 5 + ag * 1000 + bonus
        fans = toint(r[FANS]); fanpct, fanbonus = fan_bonus(fans, base)
        pt = base + fanbonus
        if pt < floor: continue
        name = r[N].strip()

        # 卒業判定：当月pt＋スタンプ獲得pt(合算)>=30万で卒業。初回検知日を記録し、猶予明けで掲載終了
        tot = pt + stamp_b.get(cid, 0)     # 合算ポイント（卒業ライン判定用）
        g = glivers.get(cid)
        if g and tot < GRAD_PT:      # 卒業ライン変更で条件を満たさなくなった人は卒業を取り消す
            del glivers[cid]; g = None
        if tot >= GRAD_PT and not g:
            if cid not in prev_beg:
                # 既に当月30万pt超で初登場＝RISE在籍/卒業済み。ビギナー猶予の対象にせず非掲載
                continue
            g = {"name": name, "graduated_on": today,
                 "grad_md": f"{int(today[5:7])}/{int(today[8:10])}",  # 卒業フラグ表示用 M/D
                 "drop_on": (datetime.strptime(today, "%Y-%m-%d")
                             + timedelta(days=GRACE_DAYS)).strftime("%Y-%m-%d")}
            glivers[cid] = g
            newgrads.append((cid, name, g["drop_on"]))
        if g and today >= g["drop_on"]:
            if today == g["drop_on"]:      # 「本日掲載終了」の報告は猶予明け当日だけ（過去卒業者を毎日再掲しない）
                dropped.append((cid, name, g["graduated_on"]))
            continue          # 猶予明け以降はビギナーから常に除外（報告はしない）

        beg.append({"cid": cid, "name": name, "pt": pt, "tot": tot,
                    "cur": cur, "ag": ag, "live": hm(r[L]), "days": days, "fans": fans, "bonus": bonus, "fanpct": fanpct, "fanbonus": fanbonus,
                    "grace_until": g["drop_on"] if g else ""})
    # スタンプ合算後(tot)で並べる＝web表示(build.pyの合算後ソート)と順位・順位差分を一致させる
    beg.sort(key=lambda x: -x["tot"])
    # 卒業フラグ用：新規卒業者の「卒業時の順位」を記録（猶予明けで消えても値は固定で残す）
    rank_of = {b["cid"]: i + 1 for i, b in enumerate(beg)}
    for cid_g, _n, _d in newgrads:
        if cid_g in glivers and "grad_rank" not in glivers[cid_g]:
            glivers[cid_g]["grad_rank"] = rank_of.get(cid_g)

    # CSV書き出し
    if dry:
        err(f"[dry-run] CSV未更新（掲載 {len(beg)}名の想定）")
    else:
        with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["name", "point", "livetime", "days", "fans", "bonus", "fanpct", "fanbonus"])
            for b in beg:
                w.writerow([b["name"], b["pt"], b["live"], b["days"], b["fans"], b["bonus"],
                            b["fanpct"], b["fanbonus"]])
        err(f"CSV {len(beg)}名")
    err(f"asof={today} 卒業猶予中={sum(1 for b in beg if b['grace_until'])}名 "
        f"新規卒業={len(newgrads)}名 掲載終了={len(dropped)}名")

    # 前回スナップショットと比較（cid基準）
    prev = {}
    if os.path.exists(SNAP):
        try:
            snap = json.load(open(SNAP))
            # {"month": YYYY-MM, "ranks": {...}}。月が変わった初日は比較しない（＝初回更新扱い）
            if snap.get("month") == month: prev = snap.get("ranks", {})
        except Exception: prev = {}
    # 卒業掲載終了で空いた枠のぶんだけ全員が繰り上がるので、
    # 前回順位は「卒業者を除いて再採番した順位」と比べる（誤って「N人抜き」と出さない）
    drop_cids = {d[0] for d in dropped}
    adj = {}
    n = 0
    for cid, v in sorted(prev.items(), key=lambda kv: kv[1].get("rank", 10**9)):
        if cid in drop_cids: continue
        n += 1; adj[cid] = n
    climbers = []
    for i, b in enumerate(beg):
        r = i + 1; pr = adj.get(b["cid"]) if prev else None
        if pr and r < pr:
            climbers.append((b["name"], pr, r, pr - r))
    climbers.sort(key=lambda x: x[2])

    # Slackメッセージ
    if bare:   # まとめ投稿に埋め込む用（メンション・「更新」表記は親側が持つ）
        msg = ["🌱 DCLビギナーランキング", URL, ""]
    else:
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
    if newgrads:
        msg.append("")
        msg.append(f"🎓 ビギナー卒業（⚡️DCL RISE⚡️へ）")
        for cid_g, name, drop in newgrads:
            m, d = drop[5:7].lstrip("0"), drop[8:10].lstrip("0")
            gr = glivers.get(cid_g, {}).get("grad_rank")
            pos = f"{gr}位で" if gr else ""
            msg.append(f"・{name}：{pos}卒業（ビギナー掲載は {m}/{d} まで）")
        if not bare: msg.append(RISE_URL)
    if dropped:
        msg.append("")
        msg.append("🏁 本日ビギナー掲載終了（⚡️DCL RISE⚡️で継続）")
        for _cid, name, _gon in dropped:
            msg.append(f"・{name}")
        if not bare: msg.append(RISE_URL)
    print("\n".join(msg))

    # スナップショット・卒業状態の更新
    if dry:
        err("[dry-run] snapshot/卒業状態は未更新")
        return
    json.dump({"month": month,
               "ranks": {b["cid"]: {"rank": i + 1, "name": b["name"], "pt": b["pt"]}
                         for i, b in enumerate(beg)}},
              open(SNAP, "w"), ensure_ascii=False, indent=0)
    gstate["month"] = month; gstate["livers"] = glivers
    json.dump(gstate, open(GRAD, "w"), ensure_ascii=False, indent=1)
    err("snapshot / 卒業状態 updated")

if __name__ == "__main__":
    main()
