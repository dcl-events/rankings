#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DCL⚔️戦国統一 ランキング／合戦帳ページ ジェネレータ
  data/sengoku.json（合戦帳スプレッドシートの ランキング／合戦帳 タブを写したもの）を読み、
  docs/tiktok-202609-sengoku.html（番付）と
  docs/tiktok-202609-sengoku-kassencho.html（合戦帳）の該当箇所だけを差し替える。
  背景・ロゴ・軍法などの装飾には触らない（marker/認識ブロックのみ置換）。

使い方:  python3 tools/sengoku_build.py
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data" / "sengoku.json"
RANK_HTML = DOCS / "tiktok-202609-sengoku.html"
KASSEN_HTML = DOCS / "tiktok-202609-sengoku-kassencho.html"

RANK_TITLE = {"A": "大名", "B": "侍大将", "C": "若武者"}   # 称号＝入会時リーグ
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}
ROSTER = {}   # 表示名(#番号) → TikTokアカウント名（参加者マスタ由来）


def yen(n):
    return f"{int(n):,}"


def disp(name):
    """表示名(#番号) を TikTokアカウント名 に解決。無ければそのまま。"""
    return ROSTER.get(name, name)


def build_rank_list(ranking):
    total = sum(int(r["兵力"]) for r in ranking) or 1
    mx = max(int(r["兵力"]) for r in ranking) if ranking else 1
    items = []
    prev = None
    for i, r in enumerate(ranking, 1):
        hei = int(r["兵力"]); lg = r["リーグ"]
        share = round(hei / total * 100, 1)
        bar = round(hei / mx * 100, 1)
        rk = RANK_TITLE.get(lg, "")
        cls = f"top g{i}" if i <= 3 else ""
        liclass = f' class="{cls}"' if cls else ""
        num_inner = f'<span class="m">{MEDAL[i]}</span>' if i <= 3 else str(i)
        num = f'<div class="num">{num_inner}<span class="rk">{rk}</span></div>'
        # gap
        if i == 1:
            gap = '<div class="gap lead">首位 ── 天下人</div>'
        elif prev is not None and hei == prev:
            gap = f'<div class="gap">同兵力で並走（{lg}リーグ）</div>'
        else:
            gap = f'<div class="gap">あと {yen(prev - hei)}兵 で1人抜き</div>'
        tm = f'<div class="tm"><span>🎖 {lg}リーグ</span><span>🏯 支配 {share}%</span></div>'
        items.append(
            f'  <li{liclass}>\n    {num}\n    <div class="body">\n'
            f'      <div class="nm">{disp(r["表示名"])}</div>\n'
            f'      {gap}\n      {tm}\n'
            f'      <div class="bar"><i style="width:{bar}%"></i></div>\n'
            f'    </div>\n    <div class="sc">{yen(hei)}<span class="unit">兵</span></div>\n  </li>')
        prev = hei
    return '<ul class="rank">\n' + "\n".join(items) + '\n</ul>'


def badge_class(judge):
    if "大下剋上" in judge:
        return "b3"
    if "下剋上" in judge:
        return "b2"
    return "b1"


def build_kassen(kassen):
    if not kassen:
        return ('<div class="empty">\n'
                '  <div class="em">🏯⚔️🏯</div>\n'
                '  <h3>いざ、開戦を待て</h3>\n'
                '  <p>まだ合戦の記録はありません。<br>\n'
                '  一騎討ちの結果が申請されると、ここに1戦ずつ刻まれます。<br>\n'
                '  「誰が誰から何兵を奪ったか」を全員が確認できます。</p>\n'
                '</div>')
    lis = []
    for r in reversed(kassen):   # 新しい順（No降順）
        b = badge_class(r["判定"])
        lis.append(
            '  <li>\n'
            f'    <div class="top"><span class="no">#{int(r["No"]):03d}</span>'
            f'<span class="badge {b}">{r["判定"]}</span>'
            f'<span class="date">{r.get("日時","")}</span></div>\n'
            f'    <div class="vs"><span class="win">{disp(r["勝者"])}</span>'
            f'<span class="x">⚔</span><span class="lose">{disp(r["敗者"])}</span></div>\n'
            f'    <div class="plunder">🔥 略奪 +{yen(r["移動兵力"])}兵</div>\n'
            f'    <div class="result">{r.get("結果","")}</div>\n  </li>')
    return '<ul class="log">\n' + "\n".join(lis) + '\n</ul>'


def build_summary(kassen):
    total = len(kassen)
    geki = sum(1 for r in kassen if r["判定"] == "下剋上成功")
    dai = sum(1 for r in kassen if "大下剋上" in r["判定"])
    return (f'<div class="summary">\n'
            f'  <div class="box"><b>{total}</b><span>総合戦数</span></div>\n'
            f'  <div class="box"><b>{geki}</b><span>下剋上</span></div>\n'
            f'  <div class="box"><b>{dai}</b><span>大下剋上</span></div>\n'
            f'</div>')


def build_overlord(ranking, kassen):
    top = ranking[0]
    total = sum(int(r["兵力"]) for r in ranking) or 1
    hei = int(top["兵力"]); share = round(hei / total * 100, 1)
    state = "暫定・現在の兵力1位" if kassen else "暫定・Aリーグ首位グループ"
    sub = (f'{top["リーグ"]}リーグ {yen(hei)}兵 ／ 天下の {share}% を支配'
           if kassen else
           f'{top["リーグ"]}リーグ {yen(hei)}兵 ／ 天下の {share}% を支配 ／ 開始時はAリーグ3名が横一線')
    return ('<div class="overlord">\n'
            f'  <div class="kanmuri">👑 天下人（{state}） 👑</div>\n'
            '  <div class="row">\n'
            '    <div class="crest">🏯</div>\n'
            '    <div class="who">\n'
            f'      <div class="nm">{disp(top["表示名"])}</div>\n'
            f'      <div class="sub">{sub}</div>\n'
            '    </div>\n'
            f'    <div class="koku"><b>{yen(hei)}</b><span>兵力</span></div>\n'
            '  </div>\n'
            '</div>')


def replace_updated(html, updated):
    return re.sub(r'最終更新: [^<]*', f'最終更新: {updated} JST', html)


def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    global ROSTER
    ROSTER = d.get("roster", {})
    updated = d.get("updated", "")
    ranking = d.get("ranking", [])
    kassen = d.get("kassen", [])

    # 番付ページ
    h = RANK_HTML.read_text(encoding="utf-8")
    h = re.sub(r'<ul class="rank">.*?</ul>', build_rank_list(ranking), h, count=1, flags=re.S)
    h = re.sub(r'<div class="overlord">.*?<span>兵力</span></div>\s*</div>\s*</div>',
               build_overlord(ranking, kassen), h, count=1, flags=re.S)
    h = replace_updated(h, updated)
    RANK_HTML.write_text(h, encoding="utf-8")

    # 合戦帳ページ
    k = KASSEN_HTML.read_text(encoding="utf-8")
    # 集計（summary は sec-head の直前まで）
    k = re.sub(r'<div class="summary">.*?</div>\s*(?=<div class="sec-head")',
               build_summary(kassen) + "\n\n", k, count=1, flags=re.S)
    # 記録（sec-head と linkbox の間）
    k = re.sub(r'(<div class="sec-head">合 戦 の 記 録</div>\n).*?(\n<div class="linkbox">)',
               lambda m: m.group(1) + "\n" + build_kassen(kassen) + "\n" + m.group(2),
               k, count=1, flags=re.S)
    k = replace_updated(k, updated)
    KASSEN_HTML.write_text(k, encoding="utf-8")

    print(f"生成完了: 番付{len(ranking)}名 / 合戦{len(kassen)}件 / 更新 {updated}")


if __name__ == "__main__":
    main()
