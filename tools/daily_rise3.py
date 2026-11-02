#!/usr/bin/env python3
"""⚡️DCL RISE3⚡️（最下位リーグ／ハートミーで伸びるリーグ）の日次更新＋順位差分。

仕様の正本: Notion「⚡ 11月からのRISE仕様書」(2026-10-31・池) の 1〜2章。
daily_rise.py / daily_beginner.py と同じ構造。違いは以下の3点だけ。

  1) 参加資格 : 前月pt < 20万（prev_month_points_<前月>.json）。記録が無い＝デビュー直後も対象。
  2) ポイント : ハートミー（＝ファンクラブのアクティブなファン）1人 +2,000pt を base に足す。
                pt =（ダイヤ×10 + Matchダイヤ×5 + Match数×1,000 + 継続50,000 + ハートミー×2,000）
                     ×（1 + アクティブファン10人ごとに1%・上限+20%）
  3) 掲載     : 当月1ダイヤ以上（ハートミーは在籍数＝ストックなので、未配信者に加点が入るのを防ぐ）

クリア（当月20万pt＝ハートミー約100人）で RISE2 へ即エントリー。
達成日を data/rise3_cleared.json に記録し、RISE2側(daily_beginner.py)が「当月RISE3クリア」として拾う。
掲載は RISE2→RISE1 と同じく「達成の翌日に掲載終了」。

月別の設定は events.json の tiktok-<YYYYMM>-rise3 から読む:
  entry_max_prev_pt(既定200000) / clear_pt(既定200000) / heartme_pt(既定2000) / list_min_dia(既定1)
  fan_bonus(既定true)

使い方:
  python3 tools/daily_rise3.py [--month 2026-11] [--date 11/1] [--bare] [--dry-run] [--asof YYYY-MM-DD]
    --bare     : まとめSlack投稿に埋め込む用（メンション無し・短い見出し）
    --dry-run  : CSV/スナップショット/クリア記録を書かずに本文だけ出す
"""
import sys, os, re, csv, glob, json
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "data", "rise3_snapshot.json")
CLEARED = os.path.join(REPO, "data", "rise3_cleared.json")
TSV_DIR = os.path.expanduser("~/Claude/tiktok-automation/out")
MENTION = "<@U0A6WU3P3LL>"   # ito_sukeaki
JST = timezone(timedelta(hours=9))

ENTRY_MAX_DEFAULT = 200000   # 参加上限（前月pt）＝RISE2の下限
CLEAR_PT_DEFAULT = 200000    # クリアライン（当月pt）
HEARTME_PT_DEFAULT = 2000    # ハートミー1人あたり
BONUS_PT = 50000             # 継続ボーナス
BONUS_DAYS = 18              # 有効LIVE日数（月間）
BONUS_HOURS = 70             # LIVE時間（月間・時間）
FAN_CAP = 200                # ファンクラブボーナスの計算上限人数（10人ごとに+1%＝最大+20%）
GRACE_DAYS = 1               # クリアの翌日に掲載終了（RISE2と同じ）


def paths_for(month):
    ym = month.replace("-", "")
    return (os.path.join(REPO, "data", f"tiktok-{ym}-rise3.csv"),
            f"https://dcl-events.github.io/rankings/tiktok-{ym}-rise3.html",
            f"https://dcl-events.github.io/rankings/tiktok-{ym}-newcomer.html")


def _event(event_id, field, default):
    try:
        doc = json.load(open(os.path.join(REPO, "data", "events.json"), encoding="utf-8"))
        for ev in doc.get("events", []):
            if ev.get("id") == event_id:
                return ev.get(field, default)
    except Exception:
        pass
    return default


def event_num(event_id, field, default):
    try:
        return int(_event(event_id, field, default))
    except Exception:
        return default


def event_flag(event_id, field, default=True):
    return bool(_event(event_id, field, default))


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
    s = str(v); h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s); sec = re.search(r"(\d+)秒", s)
    return ((int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0) / 60
            + (int(sec.group(1)) if sec else 0) / 3600)


def keizoku_bonus(days, live_raw):
    """継続ボーナス：有効LIVE日数18日以上 かつ 月間LIVE時間70時間以上で 50,000pt。"""
    return BONUS_PT if (days >= BONUS_DAYS and live_hours(live_raw) >= BONUS_HOURS) else 0


def fan_bonus(fans, base_pt):
    """ファンクラブボーナス：アクティブファン10人ごとに合計pt+1%（上限200人＝+20%）。"""
    pct = min(fans, FAN_CAP) // 10
    return pct, base_pt * pct // 100


def prev_month(month):
    y, m = int(month[:4]), int(month[5:7])
    return f"{y-1}12" if m == 1 else f"{y}{m-1:02d}"


def main():
    args = sys.argv[1:]
    month = (datetime.now(JST) - timedelta(days=2)).strftime("%Y-%m")
    date = ""; asof = ""; dry = False; bare = False
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i+1]; i += 2
        elif args[i] == "--date": date = args[i+1]; i += 2
        elif args[i] == "--asof": asof = args[i+1]; i += 2
        elif args[i] == "--dry-run": dry = True; i += 1
        elif args[i] == "--bare": bare = True; i += 1
        else: i += 1
    today = asof or datetime.now(JST).strftime("%Y-%m-%d")
    CSV_OUT, URL, RISE2_URL = paths_for(month)
    ym = month.replace("-", "")
    eid = f"tiktok-{ym}-rise3"

    ENTRY_MAX = event_num(eid, "entry_max_prev_pt", ENTRY_MAX_DEFAULT)
    CLEAR_PT  = event_num(eid, "clear_pt", CLEAR_PT_DEFAULT)
    HEART_PT  = event_num(eid, "heartme_pt", HEARTME_PT_DEFAULT)
    LIST_MIN_DIA = event_num(eid, "list_min_dia", 1)
    FAN_ON = event_flag(eid, "fan_bonus", True)
    err(f"設定: 参加=前月pt<{ENTRY_MAX:,} / クリア={CLEAR_PT:,}pt / ハートミー={HEART_PT:,}pt per 1人 "
        f"/ 掲載=当月{LIST_MIN_DIA}ダイヤ以上 / ファンクラブボーナス={'ON' if FAN_ON else 'OFF'}")

    # 前月ポイント（リーグ振り分けの正本）。無ければ全員を対象にせず中止（誤配属を防ぐ）。
    pf = os.path.join(REPO, "data", f"prev_month_points_{prev_month(month)}.json")
    if not os.path.exists(pf):
        err(f"前月ポイントが未生成: {os.path.basename(pf)} → tools/build_prev_month_points.py --month {prev_month(month)[:4]}-{prev_month(month)[4:]} を先に実行")
        sys.exit(1)
    prev_pt = {k: int(v or 0) for k, v in json.load(open(pf)).items()}

    # クリア記録（月が変わったらリセット）
    cstate = {"month": month, "livers": {}}
    if os.path.exists(CLEARED):
        try:
            loaded = json.load(open(CLEARED))
            if loaded.get("month") == month: cstate = loaded
        except Exception: pass
    clivers = cstate["livers"]

    cands = sorted(glob.glob(os.path.join(TSV_DIR, "creator_data_*.tsv")))
    if not cands:
        err("TSVなし:", TSV_DIR); sys.exit(1)
    tsv = cands[-1]
    err("source:", os.path.basename(tsv))
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    hdr = rows[0]; c = {n: k for k, n in enumerate(hdr)}
    ID = c["クリエイターID"]; N = c["ライバー名"]; D = c["ダイヤモンド"]; L = c["LIVE時間"]
    DAYS = c["有効LIVE日数"]; FANS = c["ファンクラブのアクティブなファン"]
    AG = c["LIVE Match数"]; AH = c["LIVE Matchで獲得したダイヤモンド数"]
    U = c["クリエイターのユーザー名"]

    r3 = []; newclear = []; dropped = []
    for r in rows[1:]:
        if len(r) <= max(ID, N, D, L, DAYS, FANS, AG, AH, U): continue
        cid = str(r[ID]).strip()
        if not cid.isdigit(): continue          # 退会ライバー（IDが文章）は除外
        cur = toint(r[D])
        if cur < LIST_MIN_DIA: continue         # 掲載＝当月1ダイヤ以上（未配信者にハートミー加点を入れない）
        if prev_pt.get(cid, 0) >= ENTRY_MAX: continue   # 前月20万pt以上＝RISE2/RISE1の領域

        ah = toint(r[AH]); ag = toint(r[AG]); days = toint(r[DAYS]); fans = toint(r[FANS])
        base = cur * 10 + ah * 5 + ag * 1000 + keizoku_bonus(days, r[L]) + fans * HEART_PT
        fanpct, fanbonus = fan_bonus(fans, base) if FAN_ON else (0, 0)
        pt = base + fanbonus
        name = r[N].strip()

        # クリア判定（当月20万pt）→ 達成日を記録。掲載は翌日まで。
        cv = clivers.get(cid)
        if cv and pt < CLEAR_PT:                # ライン変更で条件を外れたら取り消す
            del clivers[cid]; cv = None
        if pt >= CLEAR_PT and not cv:
            cv = {"name": name, "cleared_on": today,
                  "clear_md": f"{int(today[5:7])}/{int(today[8:10])}",
                  "drop_on": (datetime.strptime(today, "%Y-%m-%d")
                              + timedelta(days=GRACE_DAYS)).strftime("%Y-%m-%d")}
            clivers[cid] = cv
            newclear.append((cid, name, pt))
        if cv and today >= cv["drop_on"]:
            if today == cv["drop_on"]:
                dropped.append((cid, name))
            continue                            # 翌日以降はRISE3から外れる（RISE2で継続）

        r3.append({"cid": cid, "name": name, "pt": pt, "cur": cur, "ag": ag,
                   "live": hm(r[L]), "days": days, "fans": fans,
                   "bonus": keizoku_bonus(days, r[L]), "fanpct": fanpct, "fanbonus": fanbonus,
                   "heart": fans * HEART_PT, "user": str(r[U]).strip()})
    r3.sort(key=lambda x: -x["pt"])

    # CSV（他リーグと同じ列＋heart）
    if dry:
        err(f"[dry-run] CSV未更新（掲載 {len(r3)}名の想定）")
    else:
        with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "point", "livetime", "days", "fans", "bonus", "fanpct", "fanbonus", "heart", "user"])
            for b in r3:
                w.writerow([b["name"], b["pt"], b["live"], b["days"], b["fans"],
                            b["bonus"], b["fanpct"], b["fanbonus"], b["heart"], b["user"]])
    err(f"CSV {len(r3)}名（クリア新規 {len(newclear)}名／本日掲載終了 {len(dropped)}名）")

    # 前回スナップショットと比較（cid基準）
    prev = {}
    if os.path.exists(SNAP):
        try:
            _s = json.load(open(SNAP))
            prev = (_s.get("ranks") or {}) if _s.get("month") == month else {}
        except Exception: prev = {}
    drop_cids = {d[0] for d in dropped}
    adj, n = {}, 0
    for cid, v in sorted(prev.items(), key=lambda kv: kv[1].get("rank", 10**9)):
        if cid in drop_cids: continue
        n += 1; adj[cid] = n
    climbers = []
    for i2, b in enumerate(r3):
        rk = i2 + 1; pr = adj.get(b["cid"]) if prev else None
        if pr and rk < pr:
            climbers.append((b["name"], pr, rk, pr - rk))
    climbers.sort(key=lambda x: x[2])

    # Slack本文
    if bare:
        msg = ["⚡️DCL RISE3⚡️", URL, ""]
    else:
        head = f"⚡️DCL RISE3⚡️ 更新（{date}時点）" if date else "⚡️DCL RISE3⚡️ 更新"
        msg = [head, MENTION, URL, ""]
    if not prev:
        msg.append("（初回更新。順位変動の比較は次回から）")
    elif climbers:
        msg.append("📈 上のランクを抜いた人")
        for nm, pr, nr, k in climbers[:10]:
            msg.append(f"・{nm}：{pr}位→{nr}位（{k}人抜き）")
    else:
        msg.append("📊 上位を抜いた人はいませんでした（順位変動なし）")
    if newclear:
        msg.append("")
        msg.append(f"🎓 RISE3クリア（{CLEAR_PT//10000}万pt到達 → ⚡️DCL RISE2⚡️へ）")
        for _cid, nm, pt in newclear:
            msg.append(f"・{nm}：{pt:,}pt")
        if not bare: msg.append(RISE2_URL)
    if dropped:
        msg.append("")
        msg.append("🏁 本日RISE3掲載終了（⚡️DCL RISE2⚡️で継続）")
        for _cid, nm in dropped:
            msg.append(f"・{nm}")
        if not bare: msg.append(RISE2_URL)
    print("\n".join(msg))

    if dry:
        err("[dry-run] snapshot/クリア記録は未更新"); return
    json.dump({"month": month,
               "ranks": {b["cid"]: {"rank": i2 + 1, "name": b["name"], "pt": b["pt"]}
                         for i2, b in enumerate(r3)}},
              open(SNAP, "w"), ensure_ascii=False, indent=0)
    cstate["month"] = month; cstate["livers"] = clivers
    json.dump(cstate, open(CLEARED, "w"), ensure_ascii=False, indent=1)
    err("snapshot / クリア記録 updated")


if __name__ == "__main__":
    main()
