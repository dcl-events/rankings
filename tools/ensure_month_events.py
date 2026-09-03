#!/usr/bin/env python3
"""対象月のビギナー/RISEイベントが events.json に無ければ自動で作る（月替わり対応）。

前月の同種イベント（設定・rules・themeなど）をまるごとコピーし、
id / data_file / title の「◯月累計」/ period_start / period_end だけを当月に差し替える。
前月のイベントは消さない（＝最終状態で凍結アーカイブとして残る）。
CSVが無いと build.py が落ちるので、ヘッダだけのCSVも同時に用意する。

使い方: python3 tools/ensure_month_events.py --month 2026-09
"""
import sys, os, re, json, calendar

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(REPO, "data", "events.json")
DATA = os.path.join(REPO, "data")
KINDS = ("newcomer", "rise")
CSV_HEADER = "name,point,livetime,days,fans,bonus,fanpct,fanbonus\n"


def ensure(month):
    y, m = int(month[:4]), int(month[5:7])
    ym = f"{y:04d}{m:02d}"
    with open(EVENTS, encoding="utf-8") as fh:
        doc = json.load(fh)
    ids = {ev.get("id") for ev in doc["events"]}
    created = []

    for kind in KINDS:
        new_id = f"tiktok-{ym}-{kind}"
        if new_id in ids:
            continue
        # 直近（idの昇順で最後＝最新月）の同種イベントを雛形にする
        srcs = sorted((ev for ev in doc["events"]
                       if re.fullmatch(rf"tiktok-\d{{6}}-{kind}", ev.get("id", ""))),
                      key=lambda ev: ev["id"])
        if not srcs:
            sys.exit(f"雛形になる過去イベントが見つかりません: tiktok-YYYYMM-{kind}")
        ev = json.loads(json.dumps(srcs[-1]))   # deep copy
        ev["id"] = new_id
        ev["data_file"] = f"{new_id}.csv"
        ev["title"] = re.sub(r"\d+月累計", f"{m}月累計", ev.get("title", ""))
        ev["period_start"] = f"{y:04d}-{m:02d}-01"
        ev["period_end"] = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
        doc["events"].append(ev)
        created.append(f'{new_id}（雛形: {srcs[-1]["id"]}）')

        csv_path = os.path.join(DATA, ev["data_file"])
        if not os.path.exists(csv_path):
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write(CSV_HEADER)

    if created:
        with open(EVENTS, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return created


def main():
    args = sys.argv[1:]
    month = ""
    i = 0
    while i < len(args):
        if args[i] == "--month": month = args[i + 1]; i += 2
        else: sys.exit(f"unknown arg: {args[i]}")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        sys.exit("--month YYYY-MM が必要です")
    for line in ensure(month) or [f"{month}: イベントは既にあります（新規作成なし）"]:
        print(line, file=sys.stderr)


if __name__ == "__main__":
    main()
