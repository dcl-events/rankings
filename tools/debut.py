"""RISEリーグに「初めて載った日＝参加日」と「参加時の順位」を記録する共有モジュール。

各リーグの日次スクリプト（daily_rise / daily_beginner / daily_rise3）が、
表示順位（＝達成者枠の人を除いて採番した順位）を確定したあとに record_debut() を呼ぶ。
  data/debut_records.json = {"month": "YYYY-MM",
                             "leagues": {"rise1"|"rise2"|"rise3": {cid: {...}}}}
戻り値は「今日はじめて載った人」のリスト＝Slackの「🆕 新規参加」とシートの参加日/参加時順位に使う。
月が変わったら自動でリセット（当月の参加日だけを持つ）。
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "debut_records.json")


def load(month):
    doc = {"month": month, "leagues": {}}
    if os.path.exists(PATH):
        try:
            d = json.load(open(PATH, encoding="utf-8")) or {}
            if d.get("month") == month:
                doc = d
        except Exception:
            pass
    doc.setdefault("month", month)
    doc.setdefault("leagues", {})
    return doc


def record_debut(month, league, ranked, today, dry=False):
    """ranked = [{"cid","name","pt","rank"}, ...]（表示順位の昇順・達成者枠は含めない）。
    すでに記録がある人は上書きしない＝参加日と参加時順位は固定。"""
    doc = load(month)
    livers = doc["leagues"].setdefault(league, {})
    total = len(ranked)
    newly = []
    for row in ranked:
        cid = str(row.get("cid") or "").strip()
        if not cid or cid in livers:
            continue
        rec = {"name": row.get("name", ""), "date": today,
               "md": f"{int(today[5:7])}/{int(today[8:10])}",
               "rank": int(row.get("rank") or 0), "total": total,
               "pt": int(row.get("pt") or 0)}
        livers[cid] = rec
        newly.append((cid, rec))
    if not dry and newly:
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
