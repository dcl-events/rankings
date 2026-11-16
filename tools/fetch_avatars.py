#!/usr/bin/env python3
"""ライバーのアイコン画像を docs/assets/avatars/ に落とす。

取得元は tiktok-automation/collect-avatars.js が書き出す
  downloads/<プロファイル>/avatars_<ts>.json  の user_base_info.avatar（100x100 webp）。
⚠️ このURLは署名付きで時間が経つと 403 になるため、URLをページに貼らず
   画像そのものを落としてリポジトリに持つ（collect → fetch を同じ朝のうちに回す）。

対象は events.json で "icons": true のイベントのCSVに載っているユーザーだけ
（2026-11はRISE1のみ先行）。--all で取得できる全員ぶん落とす。
URL内の画像ハッシュが前回と同じならダウンロードしない＝アイコン変更時だけ更新される。

使い方: python3 tools/fetch_avatars.py [--all] [--dry-run] [--quiet]
終了コードは常に0（アイコンは装飾なので、失敗してもランキング公開は止めない）。
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avatars import av_key, av_filename  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "assets" / "avatars"
MANIFEST = DATA / "avatar_manifest.json"
DOWNLOADS = Path.home() / "Claude" / "tiktok-automation" / "downloads"
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
STALE_HOURS = 24        # これより古い avatars_*.json はURLが切れている可能性が高い
MIN_BYTES = 400         # これ未満はエラーページ等とみなす


def latest_sources():
    """プロファイルごとの最新 avatars_*.json を返す。"""
    out = []
    for d in sorted(DOWNLOADS.glob("*")):
        files = sorted(d.glob("avatars_*.json"))
        if files:
            out.append(files[-1])
    return out


def load_urls():
    """{ユーザー名キー: (avatar URL, 画像ハッシュ)} と、最も古い取得時刻を返す。"""
    urls, oldest = {}, None
    for f in latest_sources():
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️ 読めない: {f.name} ({e})", file=sys.stderr)
            continue
        mt = datetime.fromtimestamp(f.stat().st_mtime, JST)
        oldest = mt if oldest is None or mt < oldest else oldest
        n = 0
        for r in doc.get("rows") or []:
            u = av_key((r.get("raw") or {}).get("display_id") or r.get("userName"))
            av = ((r.get("raw") or {}).get("avatar") or "").strip()
            if not u or not av:
                continue
            urls[u] = (av, image_hash(av))
            n += 1
        print(f"  ・{f.parent.name}/{f.name}: {n}件（{mt:%m/%d %H:%M}取得）")
    return urls, oldest


def image_hash(url):
    """URLのうち画像を指す部分（署名を除く）。アイコン変更の検知に使う。"""
    m = re.search(r"/([0-9a-f]{16,})~", url)
    if m:
        return m.group(1)
    return re.sub(r"\?.*$", "", url)


def target_users(all_users=False):
    """events.json で icons:true のイベントのCSVに載っているユーザー名キー。"""
    if all_users:
        return None
    try:
        evs = json.load(open(DATA / "events.json", encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️ events.json が読めない: {e}", file=sys.stderr)
        return set()
    if isinstance(evs, dict):
        evs = evs.get("events") or []
    want = set()
    for ev in evs:
        if not ev.get("icons") or not ev.get("data_file"):
            continue
        p = DATA / ev["data_file"]
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                k = av_key(row.get("user"))
                if k:
                    want.add(k)
        print(f"  ・対象イベント {ev.get('id')}: 累計 {len(want)}名")
    return want


def load_manifest():
    try:
        return json.load(open(MANIFEST, encoding="utf-8"))
    except Exception:
        return {"users": {}}


def download(url, dest, dry=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/webp,image/*"})
    with urllib.request.urlopen(req, timeout=20) as res:
        body = res.read()
    if len(body) < MIN_BYTES:
        raise ValueError(f"小さすぎる({len(body)}B)")
    if not body[:4] == b"RIFF":
        raise ValueError("webpではない")
    if dry:
        return len(body)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, dest)
    return len(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="icons:true のイベントに限らず全員ぶん落とす")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("🖼 アイコン取得")
    urls, oldest = load_urls()
    if not urls:
        print("  ⚠️ avatars_*.json が無い（collect-avatars.js が走っていない）。今回は何もしない", file=sys.stderr)
        return 0
    if oldest and datetime.now(JST) - oldest > timedelta(hours=STALE_HOURS):
        print(f"  ⚠️ 取得データが古い（{oldest:%m/%d %H:%M}）。署名付きURLが切れている可能性が高い", file=sys.stderr)

    want = target_users(a.all)
    man = load_manifest()
    users = man.setdefault("users", {})
    keys = sorted(urls) if want is None else sorted(k for k in urls if k in want)
    missing = sorted(want - set(urls)) if want else []

    got = skip = fail = 0
    for k in keys:
        url, h = urls[k]
        dest = OUT / av_filename(k)
        rec = users.get(k) or {}
        if dest.exists() and rec.get("hash") == h:
            skip += 1
            continue
        try:
            n = download(url, dest, dry=a.dry_run)
            got += 1
            if not a.dry_run:
                users[k] = {"hash": h, "bytes": n, "fetched": datetime.now(JST).strftime("%Y-%m-%d %H:%M")}
            if not a.quiet:
                print(f"  ✓ {k} ({n:,}B)")
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as e:
            fail += 1
            print(f"  ✗ {k}: {e}", file=sys.stderr)

    if missing:
        print(f"  ⚠️ URLが見つからない {len(missing)}名: {', '.join(missing[:10])}"
              + ("…" if len(missing) > 10 else ""), file=sys.stderr)
    print(f"  新規/更新 {got} / 変更なし {skip} / 失敗 {fail}"
          + ("（dry-run）" if a.dry_run else ""))
    if not a.dry_run:
        man["updated"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
