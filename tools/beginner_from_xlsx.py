#!/usr/bin/env python3
"""クリエイターデータ xlsx から DCLビギナーランキング用CSVを生成する。

使い方:
  python3 tools/beginner_from_xlsx.py <xlsx1> [xlsx2 ...] [--month 2026-08] [--out data/tiktok-202608-newcomer.csv]

ビギナー仕様:
  対象 = (先月ダイヤ < 10000  または  入会が対象月) かつ 当月ダイヤ >= 1
  ※卒業(当月1万到達)は当月はリスト残留（翌月から外す運用は別途）
  表示名 = data/creator_names.json（username→表示名）。未登録IDは「未命名」として別枠表示。
"""
import sys, os, re, json, csv
import openpyxl

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = json.load(open(os.path.join(HERE, "data", "creator_names.json")))

def toint(v):
    if v in (None, "-", ""):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None

def hm(v):
    s = str(v)
    h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s)
    if h or m:
        return f"{int(h.group(1)) if h else 0}h{int(m.group(1)) if m else 0}m"
    try:
        f = float(v); return f"{int(f)}h{int(round((f - int(f)) * 60))}m"
    except (ValueError, TypeError):
        return ""

def main():
    args = sys.argv[1:]
    month = "2026-08"; out = None; files = []
    i = 0
    while i < len(args):
        if args[i] == "--month":
            month = args[i + 1]; i += 2
        elif args[i] == "--out":
            out = args[i + 1]; i += 2
        else:
            files.append(args[i]); i += 1
    seen = set(); beg = []
    for fn in files:
        ws = openpyxl.load_workbook(fn, data_only=True).active
        for r in list(ws.iter_rows(values_only=True))[1:]:
            user = r[2]
            if not user or user in seen:
                continue
            seen.add(user)
            join = str(r[5])[:10]; cur = toint(r[7]); last = r[12]
            last_new = last in (None, "-", "")
            last_i = 0 if last_new else toint(last)
            is_new = join.startswith(month)
            if cur is None or cur < 1:
                continue
            if not ((last_i is not None and last_i < 10000) or is_new):
                continue
            beg.append({"user": user, "join": join, "cur": cur,
                        "last": ("new" if last_new else last_i),
                        "live": hm(r[8]), "name": NAMES.get(user, "")})
    beg.sort(key=lambda x: -x["cur"])
    named = [b for b in beg if b["name"]]
    unnamed = [b for b in beg if not b["name"]]
    if out:
        with open(os.path.join(HERE, out), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["name", "point", "livetime"])
            for b in named:
                w.writerow([b["name"], b["cur"], b["live"]])
        print(f"wrote {out}: {len(named)} named beginners")
    print(f"\n該当 {len(beg)}名  命名済 {len(named)} / 未命名 {len(unnamed)}")
    print("=== 命名済（掲載対象）===")
    for b in named:
        grad = "🎓" if b["cur"] >= 10000 else ""
        print(f'  {b["cur"]:>7,}  {b["name"]:<18} {b["live"]:<8} {grad}')
    if unnamed:
        print("=== 未命名（英語IDのみ。表示名を付ければ掲載可）===")
        for b in unnamed:
            print(f'  {b["cur"]:>7,}  {b["user"]:<24} 入会{b["join"]} 先月{b["last"]} live {b["live"]}')

if __name__ == "__main__":
    main()
