#!/usr/bin/env python3
"""スタンプラリーの獲得pt(_manifest.json)を、ランキングリポジトリ内に同梱する
data/stamp_points.json（id→{beginner,rise}）へスリム化して書き出す。

build.py はこの in-repo ファイルを読んで合算する（GitHub Actions のランナーには
stamp-rally リポジトリが無いので、隣リポジトリ直読みだと合算されない＝この同梱が必須）。

id はランキングの snapshot(既に同一 public repo に同梱済み)と同じもの＝新たな露出増は無い。
pt が全ティア0の人は載せない（ファイルを小さく保つ）。

実行: python3 tools/make_stamp_points.py
  ランキング日次routineの build.py 直前に、stamp-rally 更新の後で呼ぶ。
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(os.path.dirname(REPO), "stamp-rally", "docs", "data", "_manifest.json")
OUT = os.path.join(REPO, "data", "stamp_points.json")


def main():
    if not os.path.exists(MANIFEST):
        print(f"! _manifest.json が見つかりません: {MANIFEST}", file=sys.stderr)
        sys.exit(1)
    man = json.load(open(MANIFEST, encoding="utf-8"))
    pts = {}
    for x in man.get("livers", []):
        p = x.get("pts") or {}
        b = int(p.get("beginner", 0) or 0)
        r = int(p.get("rise", 0) or 0)
        if b or r:
            pts[x["id"]] = {"beginner": b, "rise": r}
    out = {"source": "stamp-rally/_manifest.json", "count": len(pts), "pts": pts}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"stamp_points.json: {len(pts)}名（pt>0）を書き出し")


if __name__ == "__main__":
    main()
