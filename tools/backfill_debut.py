"""data/debut_records.json を git履歴から復元する（1回だけ使う移行スクリプト）。

日次スナップショットは毎日コミットされているので、各リーグについて
「その人が初めて載った日」と「その日の表示順位（達成者枠の人を除いた採番）」を復元できる。
達成者枠の判定には同じコミット時点のクリア記録を使う。

  python3 tools/backfill_debut.py --month 2026-11 [--dry]
"""
import json, os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "debut_records.json")
LEAGUES = {                      # league: (snapshot, 達成者枠の記録)
    "rise1": ("data/rise_snapshot.json", "data/rise_milestone.json"),
    "rise2": ("data/beginner_snapshot.json", "data/beginner_graduated.json"),
    "rise3": ("data/rise3_snapshot.json", "data/rise3_cleared.json"),
}


def git(*args, cwd=REPO):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=cwd).stdout


def show_json(h, path):
    try:
        return json.loads(git("show", f"{h}:{path}") or "{}")
    except Exception:
        return {}


def main():
    month = "2026-11"
    if "--month" in sys.argv:
        month = sys.argv[sys.argv.index("--month") + 1]
    dry = "--dry" in sys.argv
    out = {"month": month, "leagues": {}}
    for league, (snap_path, grad_path) in LEAGUES.items():
        livers = out["leagues"].setdefault(league, {})
        log = [l for l in git("log", "--reverse", "--format=%h|%s", "--", snap_path).strip().split("\n") if l]
        days = 0
        for ln in log:
            h, subject = ln.split("|", 1)
            m = re.search(r"/ (\d+)/(\d+)\)", subject)          # 「(2026-11 / 11/3)」＝データ基準日
            if not m:
                continue
            date = f"{month[:4]}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            if not date.startswith(month):
                continue
            snap = show_json(h, snap_path)
            if snap.get("month") != month:
                continue
            graded = set((show_json(h, grad_path) or {}).get("livers") or {})
            ranks = snap.get("ranks") or {}
            ranked = [cid for cid, _v in sorted(ranks.items(), key=lambda kv: kv[1].get("rank", 10**9))
                      if cid not in graded]
            total = len(ranked)
            days += 1
            for i, cid in enumerate(ranked, 1):
                if cid in livers:
                    continue
                v = ranks[cid]
                livers[cid] = {"name": v.get("name", ""), "date": date,
                               "md": f"{int(date[5:7])}/{int(date[8:10])}",
                               "rank": i, "total": total, "pt": int(v.get("pt") or 0)}
        print(f"{league}: {len(livers)}名（{days}日分のスナップショットから復元）")
    if dry:
        print("[dry] 書き込みなし"); return
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", OUT)


if __name__ == "__main__":
    main()
