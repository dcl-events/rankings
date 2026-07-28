#!/usr/bin/env python3
"""事務所イベントのランキングページを生成する静的サイトジェネレータ。

データ源は2系統:
  - source=pococha_report : ../pococha/data/event_report.csv を event_identifier で抽出
                            (Pococha Organizer API → collect.py → report.py で自動生成)
  - source=csv            : data/<data_file> を読む (TikTok LIVE などの貼り付け用)

events.json で「公開するイベント」「ランキングのスコア列」「表示モード」を制御する。
出力先 docs/ をそのまま GitHub Pages で公開できる。
"""
import csv
import json
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
POCOCHA_REPORT = ROOT.parent / "pococha" / "data" / "event_report.csv"
JST = timezone(timedelta(hours=9))
TOP_N = 20  # ランキング表示の既定上限（events.json の top_n で個別上書き可）

PF_THEME = {
    "Pococha":     {"accent": "#ff5a8a", "label": "Pococha"},
    "TikTok LIVE": {"accent": "#00c4bd", "label": "TikTok LIVE"},
}
DEFAULT_THEME = {"accent": "#6366f1", "label": "イベント"}


# ---------- データ読み込み ----------
def load_pococha_report():
    """event_report.csv を event_identifier ごとにまとめて返す。"""
    by_event = {}
    if not POCOCHA_REPORT.exists():
        return by_event
    with open(POCOCHA_REPORT, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ev = by_event.setdefault(r["event_identifier"], {
                "name": r["event_name"],
                "start": r["event_start"],
                "end": r["event_end"],
                "rows": [],
            })
            ev["rows"].append(r)
    return by_event


def rows_from_pococha(ev_cfg, report):
    src = report.get(ev_cfg["event_identifier"])
    if not src:
        raise SystemExit(f"  ✗ event_identifier が見つかりません: {ev_cfg['event_identifier']}")
    field = ev_cfg.get("score_field", "cheer_point_total")
    rows = [{"name": r["liver_name"], "score": int(r[field] or 0)} for r in src["rows"]]
    meta = {
        "title": ev_cfg.get("title") or src["name"],
        "period_start": src["start"],
        "period_end": src["end"],
    }
    return rows, meta


def rows_from_csv(ev_cfg):
    """data/<file> を読み、score_field 列でランキング行を作る。
    数値化できない/0以下の行は除外（非アクティブ・#DIV/0! を落とす）。"""
    path = DATA / ev_cfg["data_file"]
    field = ev_cfg.get("score_field", "score")
    with open(path, encoding="utf-8") as f:
        raw = [r for r in csv.DictReader(f)]
    rows = []
    for r in raw:
        try:
            v = float(r[field])
        except (ValueError, KeyError, TypeError):
            continue
        if v <= 0:
            continue
        rows.append({"name": r["name"].strip(), "score": v})
    meta = {
        "title": ev_cfg.get("title", ev_cfg["id"]),
        "period_start": ev_cfg.get("period_start", ""),
        "period_end": ev_cfg.get("period_end", ""),
    }
    return rows, meta


def medal(rank):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")


def fmt_score(score, ev_cfg):
    """display用に整形した (本体, 単位ラベル) を返す。"""
    f = ev_cfg.get("format", "int")
    label = ev_cfg.get("score_label", "")
    if f == "percent":
        return f"{score * 100:.1f}", label  # ratio(0.56) -> 56.0
    if f == "duration_sec":
        sec = int(score)
        h, m = sec // 3600, sec % 3600 // 60
        return (f"{h}時間{m:02d}分" if h else f"{m}分"), ""
    return f"{int(score):,}", label  # int


# ---------- HTML ----------
def page_shell(title, body, accent):
    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<style>
:root {{ --accent:{accent}; }}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif;
  background:#f7f7fb;color:#1a1a2e;line-height:1.5}}
.wrap{{max-width:680px;margin:0 auto;padding:24px 16px 64px}}
header.hero{{background:linear-gradient(135deg,var(--accent),#222);color:#fff;
  border-radius:18px;padding:28px 24px;margin-bottom:24px;box-shadow:0 8px 24px rgba(0,0,0,.12)}}
header.hero .pf{{font-size:13px;font-weight:700;letter-spacing:.08em;opacity:.9;text-transform:uppercase}}
header.hero h1{{margin:6px 0 10px;font-size:24px;line-height:1.3}}
header.hero .meta{{font-size:13px;opacity:.92}}
.updated{{font-size:12px;color:#8a8aa0;text-align:right;margin:-8px 0 16px}}
ul.rank{{list-style:none;margin:0;padding:0}}
ul.rank li{{display:flex;align-items:center;gap:14px;background:#fff;border-radius:14px;
  padding:14px 18px;margin-bottom:10px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
li .num{{font-size:20px;font-weight:800;min-width:42px;text-align:center;color:var(--accent)}}
li.top .num{{font-size:26px}}
li .body{{flex:1;min-width:0}}
li .nm{{font-weight:600;font-size:16px;word-break:break-all}}
li .bar{{height:7px;border-radius:4px;background:var(--accent);margin-top:6px;opacity:.85}}
li .sc{{font-variant-numeric:tabular-nums;font-weight:700;font-size:16px;white-space:nowrap}}
li .unit{{font-size:12px;color:#8a8aa0;margin-left:3px}}
.card-list a{{text-decoration:none;color:inherit}}
.card{{display:block;background:#fff;border-radius:14px;padding:18px 20px;margin-bottom:12px;
  box-shadow:0 2px 8px rgba(0,0,0,.06);border-left:5px solid var(--c)}}
.card .pf{{font-size:12px;font-weight:700;color:var(--c)}}
.card h2{{margin:4px 0 6px;font-size:18px}}
.card .meta{{font-size:13px;color:#8a8aa0}}
footer{{text-align:center;font-size:12px;color:#aaa;margin-top:40px}}
a.back{{display:inline-block;margin-bottom:16px;color:#8a8aa0;text-decoration:none;font-size:14px}}
</style></head><body><div class="wrap">
{body}
<footer>DeNA Creator Links — Event Rankings</footer>
</div></body></html>"""


def render_item(rank, r, ev_cfg, maxscore):
    display = ev_cfg.get("display", "value")
    top = "top" if rank <= 3 else ""
    num = f'{medal(rank)}<br>{rank}' if rank <= 3 else str(rank)
    name = html.escape(r["name"])
    if display == "rank":
        body = f'<div class="nm">{name}</div>'
        sc = ""
    elif display == "bar":
        pct = int(r["score"] / maxscore * 100) if maxscore else 0
        body = f'<div class="nm">{name}</div><div class="bar" style="width:{pct}%"></div>'
        sc = ""
    else:  # value
        val, unit = fmt_score(r["score"], ev_cfg)
        body = f'<div class="nm">{name}</div>'
        sc = f'<div class="sc">{val}<span class="unit">{html.escape(unit)}</span></div>'
    return (f'<li class="{top}"><div class="num">{num}</div>'
            f'<div class="body">{body}</div>{sc}</li>')


def build_event(ev_cfg, report):
    theme = PF_THEME.get(ev_cfg["platform"], DEFAULT_THEME)
    if ev_cfg["source"] == "pococha_report":
        rows, meta = rows_from_pococha(ev_cfg, report)
    else:
        rows, meta = rows_from_csv(ev_cfg)
    rows.sort(key=lambda r: r["score"], reverse=True)
    maxscore = rows[0]["score"] if rows else 0
    total = len(rows)
    top_n = ev_cfg.get("top_n", TOP_N)
    shown = rows[:top_n]
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    items = "".join(render_item(i, r, ev_cfg, maxscore) for i, r in enumerate(shown, 1))
    period = f"{meta['period_start']} 〜 {meta['period_end']}" if meta["period_start"] else ""
    cap = f"（上位{top_n}位 / 参加 {total} 名）" if total > top_n else f"／ 参加 {total} 名"
    body = f"""<a class="back" href="index.html">← イベント一覧</a>
<header class="hero">
  <div class="pf">{html.escape(theme['label'])}</div>
  <h1>{html.escape(meta['title'])}</h1>
  <div class="meta">{period} {cap}</div>
</header>
<div class="updated">最終更新: {now} JST</div>
<ul class="rank">{items}</ul>"""
    (DOCS / f"{ev_cfg['id']}.html").write_text(
        page_shell(meta["title"], body, theme["accent"]), encoding="utf-8")
    return meta


def build_index(cards_meta):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    cards = []
    for ev_cfg, meta in cards_meta:
        theme = PF_THEME.get(ev_cfg["platform"], DEFAULT_THEME)
        period = f"{meta['period_start']} 〜 {meta['period_end']}" if meta["period_start"] else ""
        cards.append(
            f'<a href="{ev_cfg["id"]}.html"><div class="card" style="--c:{theme["accent"]}">'
            f'<div class="pf">{html.escape(theme["label"])}</div>'
            f'<h2>{html.escape(meta["title"])}</h2>'
            f'<div class="meta">{period}</div></div></a>')
    body = f"""<header class="hero">
  <div class="pf" style="text-transform:lowercase">DeNA Creator Links</div>
  <h1>事務所イベント ランキング</h1>
  <div class="meta">Pococha ／ TikTok LIVE</div>
</header>
<div class="updated">最終更新: {now} JST</div>
<div class="card-list">{''.join(cards)}</div>"""
    (DOCS / "index.html").write_text(
        page_shell("事務所イベント ランキング", body, DEFAULT_THEME["accent"]), encoding="utf-8")


def main():
    DOCS.mkdir(exist_ok=True)
    cfg = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    report = load_pococha_report()
    cards_meta = []
    for ev_cfg in cfg["events"]:
        meta = build_event(ev_cfg, report)
        cards_meta.append((ev_cfg, meta))
        print(f"  生成: {ev_cfg['id']}.html  [{ev_cfg['platform']}] {meta['title']} ({ev_cfg.get('display','value')})")
    build_index(cards_meta)
    print(f"  生成: index.html  (イベント {len(cards_meta)} 件)")
    print("完了 → docs/ を GitHub Pages で公開できます")


if __name__ == "__main__":
    main()
