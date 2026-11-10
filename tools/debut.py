"""RISEリーグに「初めて載った日＝参加日」と「参加時の順位」を記録する共有モジュール。

各リーグの日次スクリプト（daily_rise / daily_beginner / daily_rise3）が、
表示順位（＝達成者枠の人を除いて採番した順位）を確定したあとに record_debut() を呼ぶ。
  data/debut_records.json = {"month": "YYYY-MM",
                             "leagues": {"rise1"|"rise2"|"rise3": {cid: {...}}}}
戻り値は「今日はじめて載った人」のリスト＝Slackの「🆕 新規参加」とシートの参加日/参加時順位に使う。
★月が変わっても消さない・既にある人は上書きしない＝参加日と参加時順位は一度入ったら固定。
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PATH = os.path.join(DATA_DIR, "debut_records.json")
FIRST_BC = os.path.join(DATA_DIR, "first_broadcast_resolved.json")
WINDOW_DAYS = 30   # 初配信からこの日数以内にランキングに載った人＝「新規参加（デビュー）」とみなす


def load(month=None):
    """記録を読む。★月が変わっても消さない＝参加日と参加時順位は一度入ったら永続。
    旧形式（トップレベルの "month" が当月の月だけを持つ）も読めるように移行する。"""
    doc = {"leagues": {}}
    if os.path.exists(PATH):
        try:
            d = json.load(open(PATH, encoding="utf-8")) or {}
            if isinstance(d, dict) and d.get("leagues") is not None:
                doc = d
                old_month = d.get("month")          # 旧形式：各レコードに月が無い
                if old_month:
                    for livers in doc["leagues"].values():
                        for rec in livers.values():
                            rec.setdefault("month", old_month)
        except Exception:
            pass
    doc.setdefault("leagues", {})
    doc.pop("month", None)
    return doc


def record_debut(month, league, ranked, today, dry=False):
    """ranked = [{"cid","name","pt","rank"}, ...]（表示順位の昇順・達成者枠は含めない）。
    すでに記録がある人は上書きしない＝参加日と参加時順位は固定。"""
    doc = load()
    livers = doc["leagues"].setdefault(league, {})
    total = len(ranked)
    newly = []
    for row in ranked:
        cid = str(row.get("cid") or "").strip()
        if not cid or cid in livers:
            continue                     # ★既にある人は絶対に上書きしない（参加日・参加時順位は固定）
        rec = {"name": row.get("name", ""), "date": today, "month": month,
               "md": f"{int(today[5:7])}/{int(today[8:10])}",
               "rank": int(row.get("rank") or 0), "total": total,
               "pt": int(row.get("pt") or 0)}
        livers[cid] = rec
        newly.append((cid, rec))
    if not dry and newly:
        doc["updated"] = today
        json.dump(doc, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return newly


def slack_lines(newly, uh=None, label="🆕 新規参加"):
    """Slack本文用の行（見出し＋1人1行）。uh(cid) はユーザー名「｜@xxx」を返す関数。"""
    if not newly:
        return []
    out = ["", label]
    for cid, rec in newly:
        handle = uh(cid) if uh else ""
        out.append(f"・{rec['name']}{handle}：参加時 {rec['rank']}位/{rec['total']}人"
                   f"（{rec['pt']:,}pt）")
    return out


def load_first_broadcast():
    """初配信日の確定版 {cid: "YYYY/MM/DD"}。stamp-rally の gen_tasksheet が毎朝書き出す
    （①手動オーバーライド → ②マスターU列 → ③日次TSVからの再構成 の優先順で解決済み）。"""
    try:
        return json.load(open(FIRST_BC, encoding="utf-8")) or {}
    except Exception:
        return {}


def is_new_debut(cid, rec, first_bc=None, window_days=WINDOW_DAYS):
    """「本当に初配信してからランキングに載った人」か。
    初配信からランキング初掲載までが window_days 以内なら True。
    （例：初配信10/23→11/1掲載=9日→True／初配信2月→11/8に復帰で掲載=261日→False）
    初配信日が未登録の人は判定できないので False（取りこぼしは呼び出し側が件数で報告する）。"""
    from datetime import datetime
    if first_bc is None:
        first_bc = load_first_broadcast()
    fb = (first_bc or {}).get(str(cid), "")
    if not fb or not rec.get("date"):
        return False
    try:
        f = datetime.strptime(fb.replace("/", "-"), "%Y-%m-%d")
        d = datetime.strptime(rec["date"], "%Y-%m-%d")
    except ValueError:
        return False
    return (d - f).days <= window_days          # 負の日数（再構成のズレ）も通す


def filter_new_debuts(newly, first_bc=None, window_days=WINDOW_DAYS):
    """newly を「本当のデビュー組」だけに絞る。戻り値 (絞った結果, 初配信日が未登録で判定できなかった人)。"""
    if first_bc is None:
        first_bc = load_first_broadcast()
    keep, unknown = [], []
    for cid, rec in newly:
        if str(cid) not in (first_bc or {}):
            unknown.append((cid, rec)); continue
        if is_new_debut(cid, rec, first_bc, window_days):
            keep.append((cid, rec))
    return keep, unknown


def is_month_debut(cid, rec, first_bc=None):
    """「ランキングに参加した月に初配信した人」か（シートの参加日/参加時順位を出す条件）。
    例：初配信11/4→11/5参加=True／初配信10/23→11/1参加=False（前月デビュー）／初配信日が未登録=False。
    ※月をまたぐ境目（初配信11/30→12/1参加）は False になる。必要なら呼び出し側で足す。"""
    fb = (first_bc if first_bc is not None else load_first_broadcast()).get(str(cid), "")
    d = rec.get("date") or ""
    if not fb or not d:
        return False
    return fb.replace("/", "-")[:7] == d[:7]
