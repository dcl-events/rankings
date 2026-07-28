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

# プラットフォーム別テーマ。accent=順位番号/チップ/カード左バー上, accent2=グラデ相方, hero=ヒーロー背景
PF_THEME = {
    # Pococha は青白（ブルー×ホワイト）イメージ
    "Pococha":     {"accent": "#1668c9", "accent2": "#7fc4f0", "label": "Pococha",
                    "hero": "linear-gradient(120deg,#0d5bbf 0%,#2b8fe6 52%,#8fd0f5 100%)"},
    # TikTok LIVE は DCL ブランドの暖色（オレンジ→イエロー）
    "TikTok LIVE": {"accent": "#eb5000", "accent2": "#facd00", "label": "TikTok LIVE",
                    "hero": "linear-gradient(115deg,#eb5000 0%,#ff7a1a 46%,#facd00 100%)"},
}
# 一覧トップ（DeNA Creator Links ブランド）= ロゴの全色を使ったお祭り感マルチカラー
DEFAULT_THEME = {"accent": "#eb5000", "accent2": "#facd00", "label": "イベント",
                 "hero": "linear-gradient(120deg,#7c3aed 0%,#f062b0 30%,#f2600f 66%,#ffc400 100%)"}


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
def page_shell(title, body, theme):
    accent = theme["accent"]
    accent2 = theme.get("accent2", accent)
    hero = theme.get("hero", DEFAULT_THEME["hero"])
    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<link rel="icon" href="assets/dcl_mark.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@500;600;700;800&family=Noto+Sans+JP:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --accent:{accent}; --accent2:{accent2}; --hero:{hero};
  --brand-orange:#eb5000; --brand-yellow:#facd00; --brand-pink:#f177c4;
  --ink:#333; --muted:#9a8f86; --cream:#fff9ef; --line:#f0e7dd;
  --gold:#f6b400; --silver:#b9b3ac; --bronze:#d08a4e;
}}
*{{box-sizing:border-box}}
body{{margin:0;
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  background:
    radial-gradient(1200px 380px at 12% -8%, #ffe9c9 0%, rgba(255,233,201,0) 60%),
    radial-gradient(1000px 360px at 100% 4%, #ffe0ed 0%, rgba(255,224,237,0) 55%),
    #fffdf8;
  color:var(--ink);line-height:1.5;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:680px;margin:0 auto;padding:22px 16px 72px}}

/* ブランドヘッダー（ロゴ） */
.brandbar{{display:flex;justify-content:center;margin:8px 0 20px}}
.brandbar img{{height:34px;width:auto}}

/* ヒーロー */
header.hero{{position:relative;overflow:hidden;color:#fff;border-radius:22px;
  padding:26px 24px;margin-bottom:22px;
  background:var(--hero);
  box-shadow:0 14px 30px rgba(0,0,0,.20)}}
header.hero::after{{content:"";position:absolute;right:-40px;top:-60px;width:200px;height:200px;
  border-radius:50%;background:rgba(255,255,255,.16)}}
/* トップ専用：紙吹雪風のお祭りあしらい */
.index-hero::before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.9;
  background:
    radial-gradient(circle at 70% 18%, #fff 0 5px, transparent 6px),
    radial-gradient(circle at 88% 34%, #ffe45e 0 6px, transparent 7px),
    radial-gradient(circle at 78% 58%, rgba(255,255,255,.85) 0 4px, transparent 5px),
    radial-gradient(circle at 94% 72%, #fff 0 4px, transparent 5px),
    radial-gradient(circle at 66% 82%, #ffd0ec 0 5px, transparent 6px),
    radial-gradient(circle at 86% 88%, rgba(255,255,255,.8) 0 3px, transparent 4px),
    radial-gradient(circle at 96% 50%, rgba(255,255,255,.7) 0 3px, transparent 4px)}}
.index-hero h1{{text-shadow:0 2px 10px rgba(0,0,0,.16)}}
header.hero .pf{{position:relative;font-family:'Jost',sans-serif;font-size:12px;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase;opacity:.95}}
header.hero h1{{position:relative;margin:8px 0 10px;font-size:26px;line-height:1.28;
  font-weight:800;letter-spacing:.01em}}
header.hero .meta{{position:relative;font-size:13px;opacity:.95;font-weight:500}}
.chip{{display:inline-block;background:rgba(255,255,255,.22);border-radius:999px;
  padding:3px 12px;font-size:12px;font-weight:700;margin-bottom:4px}}

.updated{{font-size:12px;color:var(--muted);text-align:right;margin:-6px 2px 16px}}

/* ランキング */
ul.rank{{list-style:none;margin:0;padding:0}}
ul.rank li{{display:flex;align-items:center;gap:14px;background:#fff;border-radius:16px;
  padding:14px 16px;margin-bottom:10px;border:1px solid var(--line);
  box-shadow:0 4px 14px rgba(120,80,20,.05)}}
li .num{{font-family:'Jost',sans-serif;font-size:20px;font-weight:700;min-width:46px;
  text-align:center;color:var(--accent);line-height:1.05}}
li .num .m{{font-size:20px}}
li.top{{border-color:transparent}}
li.g1{{background:linear-gradient(100deg,#fff6d8,#fff)}}
li.g2{{background:linear-gradient(100deg,#f3f1ee,#fff)}}
li.g3{{background:linear-gradient(100deg,#fbe8d6,#fff)}}
li.g1 .num{{color:var(--gold)}} li.g2 .num{{color:var(--silver)}} li.g3 .num{{color:var(--bronze)}}
li.top .num{{font-size:22px}}
li .body{{flex:1;min-width:0}}
li .nm{{font-weight:700;font-size:16px;word-break:break-word}}
li .bar{{height:7px;border-radius:4px;margin-top:7px;
  background:linear-gradient(90deg,var(--brand-orange),var(--brand-yellow))}}
li .sc{{font-family:'Jost',sans-serif;font-variant-numeric:tabular-nums;font-weight:700;
  font-size:18px;white-space:nowrap;color:var(--ink)}}
li .unit{{font-family:'Noto Sans JP',sans-serif;font-size:11px;color:var(--muted);
  margin-left:3px;font-weight:500}}

/* イベント一覧カード */
.card-list a{{text-decoration:none;color:inherit}}
.card{{position:relative;display:block;background:#fff;border-radius:18px;padding:18px 20px 18px 22px;
  margin-bottom:14px;border:1px solid var(--line);box-shadow:0 6px 18px rgba(120,80,20,.06);
  transition:transform .15s ease, box-shadow .15s ease;overflow:hidden}}
.card::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;
  background:linear-gradient(180deg,var(--c),var(--c2))}}
.card:hover{{transform:translateY(-2px);box-shadow:0 12px 26px rgba(0,0,0,.14)}}
.card .pf{{display:inline-block;font-family:'Jost',sans-serif;font-size:11px;font-weight:700;
  letter-spacing:.06em;color:#fff;background:var(--c);border-radius:999px;padding:3px 11px}}
.card h2{{margin:9px 0 5px;font-size:19px;font-weight:800}}
.card .meta{{font-size:13px;color:var(--muted);font-weight:500}}
.card .arrow{{position:absolute;right:18px;top:50%;transform:translateY(-50%);
  color:var(--c);font-size:20px}}

footer{{text-align:center;font-size:12px;color:var(--muted);margin-top:44px;
  font-family:'Jost',sans-serif;letter-spacing:.04em}}
a.back{{display:inline-block;margin-bottom:14px;color:var(--muted);text-decoration:none;
  font-size:14px;font-weight:600}}
a.back:hover{{color:var(--brand-orange)}}
</style></head><body><div class="wrap">
<div class="brandbar"><a href="index.html"><img src="assets/dcl_logo.png" alt="DeNA Creator Links"></a></div>
{body}
<footer>DeNA Creator Links — Event Rankings</footer>
</div></body></html>"""


def render_item(rank, r, ev_cfg, maxscore):
    display = ev_cfg.get("display", "value")
    top = f"top g{rank}" if rank <= 3 else ""
    num = f'<span class="m">{medal(rank)}</span><br>{rank}' if rank <= 3 else str(rank)
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
  <div class="chip">{html.escape(theme['label'])}</div>
  <h1>{html.escape(meta['title'])}</h1>
  <div class="meta">{period}　{cap}</div>
</header>
<div class="updated">最終更新: {now} JST</div>
<ul class="rank">{items}</ul>"""
    (DOCS / f"{ev_cfg['id']}.html").write_text(
        page_shell(meta["title"], body, theme), encoding="utf-8")
    return meta


def build_index(cards_meta):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    # 開催日が新しい順（開始日→終了日の降順）に並べる。日付は YYYY-MM-DD なので文字列比較でOK
    cards_meta = sorted(
        cards_meta,
        key=lambda cm: (cm[1].get("period_start", ""), cm[1].get("period_end", "")),
        reverse=True)
    cards = []
    for ev_cfg, meta in cards_meta:
        theme = PF_THEME.get(ev_cfg["platform"], DEFAULT_THEME)
        period = f"{meta['period_start']} 〜 {meta['period_end']}" if meta["period_start"] else ""
        cards.append(
            f'<a href="{ev_cfg["id"]}.html"><div class="card" style="--c:{theme["accent"]};--c2:{theme.get("accent2", theme["accent"])}">'
            f'<span class="arrow">›</span>'
            f'<div class="pf">{html.escape(theme["label"])}</div>'
            f'<h2>{html.escape(meta["title"])}</h2>'
            f'<div class="meta">{period}</div></div></a>')
    body = f"""<header class="hero index-hero">
  <div class="chip">DeNA Creator Links</div>
  <h1>事務所イベント ランキング</h1>
  <div class="meta">Pococha ／ TikTok LIVE</div>
</header>
<div class="updated">最終更新: {now} JST</div>
<div class="card-list">{''.join(cards)}</div>"""
    (DOCS / "index.html").write_text(
        page_shell("事務所イベント ランキング", body, DEFAULT_THEME), encoding="utf-8")


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
