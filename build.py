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
    time_field = ev_cfg.get("time_field")  # 任意: 配信時間などの補助列
    days_field = ev_cfg.get("days_field")  # 任意: 有効LIVE日数（配信時間の横に出す）
    fans_field = ev_cfg.get("fans_field")  # 任意: ファンクラブのアクティブなファン
    bonus_field = ev_cfg.get("bonus_field")  # 任意: 継続ボーナス(pt)。>0 の人にだけバッジを出す
    fanpct_field = ev_cfg.get("fanpct_field")      # 任意: ファンクラブボーナス率(%)
    fanbonus_field = ev_cfg.get("fanbonus_field")  # 任意: ファンクラブボーナス(pt)
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
        row = {"name": r["name"].strip(), "score": v}
        if time_field:
            row["time"] = (r.get(time_field) or "").strip()
        if days_field:
            row["days"] = (r.get(days_field) or "").strip()
        if fans_field:
            row["fans"] = (r.get(fans_field) or "").strip()
        if bonus_field:
            try: row["bonus"] = int(float(r.get(bonus_field) or 0))
            except ValueError: row["bonus"] = 0
        for key, fld in (("fanpct", fanpct_field), ("fanbonus", fanbonus_field)):
            if fld:
                try: row[key] = int(float(r.get(fld) or 0))
                except ValueError: row[key] = 0
        rows.append(row)
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
DARK_CSS = """
/* ダークテーマ（events.json の theme.dark:true で有効） */
body{background:
    radial-gradient(1100px 420px at 10% -10%, #24242a 0%, rgba(36,36,42,0) 62%),
    radial-gradient(900px 380px at 100% 2%, #2a1a22 0%, rgba(42,26,34,0) 58%),
    #0b0b0d;color:var(--ink)}
.brandbar img{filter:none}   /* ロゴは無加工。ダーク時は公式のダークモード用ロゴを使う */
header.hero{box-shadow:0 16px 34px rgba(0,0,0,.55);
  border:1px solid rgba(255,255,255,.10)}
header.hero::after{background:rgba(255,255,255,.06)}
details.rules{background:#141418;border-color:#26262d;box-shadow:0 6px 18px rgba(0,0,0,.35)}
.rsec li{color:#d8d8de}
ul.rank li{background:#141418;border-color:#26262d;box-shadow:0 6px 18px rgba(0,0,0,.35)}
li.g1{background:linear-gradient(100deg,#2b230f,#141418)}
li.g2{background:linear-gradient(100deg,#232327,#141418)}
li.g3{background:linear-gradient(100deg,#2a1d13,#141418)}
li.top{border-color:rgba(255,255,255,.14)}
li .sc{color:#fff}
.linkbox a{background:#141418;border-color:#26262d;box-shadow:0 6px 18px rgba(0,0,0,.35)}
li .gap{color:var(--accent)}
footer{color:#6f6f78}
"""


def page_shell(title, body, theme):
    accent = theme["accent"]
    accent2 = theme.get("accent2", accent)
    hero = theme.get("hero", DEFAULT_THEME["hero"])
    favicon = theme.get("favicon", "assets/dcl_mark.png")
    dark = theme.get("dark")
    ink, muted, line = ("#f1f1f4", "#9a9aa4", "#26262d") if dark else ("#333", "#9a8f86", "#f0e7dd")
    dark_css = DARK_CSS if dark else ""
    brandlogo = theme.get("brandlogo") or ("assets/dcl_logo_dark.png" if dark else "assets/dcl_logo.png")
    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<link rel="icon" href="{favicon}">
<link rel="apple-touch-icon" href="{favicon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@500;600;700;800&family=Noto+Sans+JP:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --accent:{accent}; --accent2:{accent2}; --hero:{hero};
  --brand-orange:#eb5000; --brand-yellow:#facd00; --brand-pink:#f177c4;
  --ink:{ink}; --muted:{muted}; --cream:#fff9ef; --line:{line};
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
header.hero .herologo{{position:relative;display:block;width:min(100%,340px);height:auto;
  margin:12px 0 8px;filter:drop-shadow(0 4px 14px rgba(0,0,0,.45))}}
header.hero .herosub{{position:relative;font-size:19px;font-weight:800;margin:0 0 8px}}
.chip{{display:inline-block;background:rgba(255,255,255,.22);border-radius:999px;
  padding:3px 12px;font-size:12px;font-weight:700;margin-bottom:4px}}

.updated{{font-size:12px;color:var(--muted);text-align:right;margin:-6px 2px 16px}}

/* 折りたたみルール */
details.rules{{background:#fff;border:1px solid var(--line);border-radius:16px;
  margin-bottom:16px;overflow:hidden;box-shadow:0 4px 14px rgba(120,80,20,.05)}}
details.rules>summary{{list-style:none;cursor:pointer;padding:14px 16px;
  font-weight:800;font-size:14px;color:var(--accent);user-select:none}}
details.rules>summary::-webkit-details-marker{{display:none}}
details.rules>summary::after{{content:"▼";float:right;font-size:10px;opacity:.6;
  transition:transform .2s}}
details.rules[open]>summary::after{{transform:rotate(180deg)}}
.rbody{{padding:0 16px 12px}}
.rsec{{margin-top:12px}}
.rsec .rh{{font-weight:800;font-size:13px;margin-bottom:5px;
  padding-left:9px;border-left:3px solid var(--accent)}}
.rsec ul{{margin:0;padding-left:1.15em}}
.rsec li{{font-size:13px;line-height:1.75;color:var(--ink);word-break:break-word}}

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
li .gap{{margin-top:4px;font-size:12px;font-weight:600;color:var(--brand-orange);
  font-family:'Noto Sans JP',sans-serif}}
li .tm{{margin-top:3px;font-size:12px;font-weight:500;color:var(--muted);
  font-family:'Noto Sans JP',sans-serif;
  display:flex;flex-wrap:wrap;gap:1px 10px}}
li .tm span{{white-space:nowrap}}
li .tm .bns{{color:var(--brand-orange);font-weight:700}}
li .bar{{height:7px;border-radius:4px;margin-top:7px;
  background:linear-gradient(90deg,var(--brand-orange),var(--brand-yellow))}}
li .sc{{font-family:'Jost',sans-serif;font-variant-numeric:tabular-nums;font-weight:700;
  font-size:18px;white-space:nowrap;color:var(--ink)}}
li .unit{{font-family:'Noto Sans JP',sans-serif;font-size:11px;color:var(--muted);
  margin-left:3px;font-weight:500}}

/* ランキング下部のリンク */
.linkbox{{margin:18px 0 4px}}
.linkbox a{{display:flex;align-items:center;justify-content:space-between;gap:10px;
  background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px 18px;
  text-decoration:none;color:var(--ink);font-weight:700;font-size:14px;
  box-shadow:0 4px 14px rgba(120,80,20,.05);transition:transform .15s ease,box-shadow .15s ease}}
.linkbox a:hover{{transform:translateY(-2px);box-shadow:0 10px 22px rgba(0,0,0,.14)}}
.linkbox a::after{{content:"›";color:var(--accent);font-size:20px;line-height:1}}

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
{dark_css}
</style></head><body><div class="wrap">
<div class="brandbar"><a href="index.html"><img src="{brandlogo}" alt="DeNA Creator Links"></a></div>
{body}
<footer>DeNA Creator Links — Event Rankings</footer>
</div></body></html>"""


def render_item(rank, r, ev_cfg, maxscore, gap_text=""):
    display = ev_cfg.get("display", "value")
    top = f"top g{rank}" if rank <= 3 else ""
    num = f'<span class="m">{medal(rank)}</span><br>{rank}' if rank <= 3 else str(rank)
    name = html.escape(r["name"])
    gap = f'<div class="gap">{html.escape(gap_text)}</div>' if gap_text else ""
    tm = r.get("time")
    dy = r.get("days")
    fn = r.get("fans")
    parts = []
    if tm: parts.append(f"⏱ 配信 {html.escape(tm)}")
    if dy: parts.append(f"📅 有効LIVE {html.escape(dy)}日")
    if fn: parts.append(f"💛 アクティブファン {html.escape(fn)}人")
    # ファンクラブボーナス(fanpct/fanbonus)は人数表記があれば足りるのでカードには出さない
    bn = r.get("bonus") or 0
    if bn: parts.append(f'<b class="bns">🔥 継続ボーナス +{bn:,}pt</b>')
    tline = ('<div class="tm">' + "".join(f"<span>{x}</span>" for x in parts) + "</div>") if parts else ""
    sub = gap + tline
    if display == "rank":
        body = f'<div class="nm">{name}</div>{sub}'
        sc = ""
    elif display == "bar":
        pct = int(r["score"] / maxscore * 100) if maxscore else 0
        body = f'<div class="nm">{name}</div><div class="bar" style="width:{pct}%"></div>{sub}'
        sc = ""
    else:  # value
        val, unit = fmt_score(r["score"], ev_cfg)
        body = f'<div class="nm">{name}</div>{sub}'
        sc = f'<div class="sc">{val}<span class="unit">{html.escape(unit)}</span></div>'
    return (f'<li class="{top}"><div class="num">{num}</div>'
            f'<div class="body">{body}</div>{sc}</li>')


def rules_html(ev_cfg):
    """events.json の rules(セクション配列) を折りたたみ(details)で描画。無ければ空。"""
    rules = ev_cfg.get("rules")
    if not rules:
        return ""
    secs = []
    for s in rules:
        items = "".join(f"<li>{html.escape(str(it))}</li>" for it in s.get("items", []))
        secs.append(f'<div class="rsec"><div class="rh">{html.escape(s.get("h",""))}</div>'
                    f'<ul>{items}</ul></div>')
    return ('<details class="rules"><summary>📖 ランキングのルール</summary>'
            f'<div class="rbody">{"".join(secs)}</div></details>')


def links_html(ev_cfg):
    """events.json の links([{label,url}])をランキング下部にボタンで並べる。無ければ空。"""
    links = ev_cfg.get("links")
    if not links:
        return ""
    items = "".join(
        f'<a href="{html.escape(l["url"])}" target="_blank" rel="noopener">'
        f'<span>{html.escape(l["label"])}</span></a>' for l in links)
    return f'<div class="linkbox">{items}</div>'


def build_event(ev_cfg, report):
    # プラットフォーム既定テーマに、events.json の theme(accent/accent2/hero/dark/favicon/logo)を上書き
    theme = dict(PF_THEME.get(ev_cfg["platform"], DEFAULT_THEME))
    theme.update(ev_cfg.get("theme", {}))
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
    # 次の1人までの距離（show_gap:true のとき各行に表示）
    gap_unit = ev_cfg.get("score_label", "")
    def gap_for(i, r):
        if not ev_cfg.get("show_gap"):
            return ""
        if i == 1:
            return "首位"
        need = int(round(shown[i - 2]["score"] - r["score"])) + 1
        return f"あと {need:,}{gap_unit} で1人抜き"
    items = "".join(render_item(i, r, ev_cfg, maxscore, gap_for(i, r))
                    for i, r in enumerate(shown, 1))
    period = f"{meta['period_start']} 〜 {meta['period_end']}" if meta["period_start"] else ""
    # show_count:false で参加人数の表記を消せる（上位N位のみ表示中はその旨だけ出す）
    if ev_cfg.get("show_count", True):
        cap = f"（上位{top_n}位 / 参加 {total} 名）" if total > top_n else f"／ 参加 {total} 名"
    else:
        cap = f"（上位{top_n}位）" if total > top_n else ""
    # theme.logo があればタイトル1行目をロゴ画像に差し替え、2行目以降をサブタイトルにする
    tlines = meta["title"].split("\n")
    if theme.get("logo"):
        sub = "<br>".join(html.escape(x) for x in tlines[1:])
        head = (f'<img class="herologo" src="{theme["logo"]}" alt="{html.escape(tlines[0])}">'
                + (f'<div class="herosub">{sub}</div>' if sub else ""))
    else:
        head = f"<h1>{html.escape(meta['title']).replace(chr(10), '<br>')}</h1>"
    body = f"""<a class="back" href="index.html">← イベント一覧</a>
<header class="hero">
  <div class="chip">{html.escape(theme['label'])}</div>
  {head}
  <div class="meta">{period}　{cap}</div>
</header>
<div class="updated">最終更新: {now} JST</div>
{rules_html(ev_cfg)}
<ul class="rank">{items}</ul>
{links_html(ev_cfg)}"""
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
        theme = dict(PF_THEME.get(ev_cfg["platform"], DEFAULT_THEME))
        theme.update(ev_cfg.get("theme", {}))   # 個別テーマ（RISEの黒×オレンジ等）を一覧カードにも反映
        period = f"{meta['period_start']} 〜 {meta['period_end']}" if meta["period_start"] else ""
        cards.append(
            f'<a href="{ev_cfg["id"]}.html"><div class="card" style="--c:{theme["accent"]};--c2:{theme.get("accent2", theme["accent"])}">'
            f'<span class="arrow">›</span>'
            f'<div class="pf">{html.escape(theme["label"])}</div>'
            f'<h2>{html.escape(meta["title"])}</h2>'
            f'<div class="meta">{period}</div></div></a>')
    body = f"""<header class="hero index-hero">
  <div class="chip">DeNA Creator Links</div>
  <h1>事務所イベント</h1>
  <div class="meta">Pococha ／ TikTok LIVE</div>
</header>
<div class="updated">最終更新: {now} JST</div>
<div class="card-list">{''.join(cards)}</div>"""
    (DOCS / "index.html").write_text(
        page_shell("事務所イベント", body, DEFAULT_THEME), encoding="utf-8")


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
