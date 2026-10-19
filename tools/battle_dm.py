#!/usr/bin/env python3
"""課題申告シート_Claude の N列「バトルDM可」を読み、data/battle_dm.json に書き出す。

  値が「可」の人だけを載せる（ユーザー名キー＋クリエイターIDキーの両方）。
  build.py はこの in-repo ファイルを読んで、ランキング/昇格枠のTikTokリンクの左に
  「⚔ バトルDM可」バッジを出す。列の入力は人が行う（スクリプトは読むだけ）。

  実行: ~/Claude/pococha/.venv/bin/python tools/battle_dm.py
    ランキング日次routineの build.py 直前に呼ぶ。失敗しても前回値のまま続行する。
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "battle_dm.json")
CREDS = os.environ.get("SERVICE_ACCOUNT_FILE", "/Users/sukeaki.ito/Claude/pococha/service_account.json")
SPREADSHEET_ID = "1A-WSX4mteR-E5kY8V82dTUqoTcD0GDLA0Uq0qiDTzh4"
TASK_GID = 1676003252
COL = "バトルDM可"
OK_VALUES = {"可", "OK", "ok", "○", "◯", "TRUE", "true", "✓"}


def main():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sh = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    ws = [w for w in sh.worksheets() if w.id == TASK_GID][0]
    vals = ws.get_all_values()
    hdr = vals[1] if len(vals) > 1 else []
    if COL not in hdr:
        print(f"! 見出し『{COL}』が無い（列が消された？）", file=sys.stderr); sys.exit(1)
    ci, cu, cid = hdr.index(COL), hdr.index("クリエイターのユーザー名"), hdr.index("クリエイターID")
    users, ids = {}, {}
    for r in vals[2:]:
        if len(r) <= ci or (r[ci] or "").strip() not in OK_VALUES:
            continue
        u = (r[cu] or "").strip().lstrip("@").lower()
        i = (r[cid] or "").strip()
        if u: users[u] = True
        if i: ids[i] = True
    json.dump({"users": users, "ids": ids}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"battle_dm.json: 可 {len(users)}名")


if __name__ == "__main__":
    main()
