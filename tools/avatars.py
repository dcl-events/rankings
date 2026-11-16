#!/usr/bin/env python3
"""ライバーのアイコン画像のファイル名ルール（build.py と fetch_avatars.py の共通定義）。

画像は docs/assets/avatars/<ユーザー名>.webp に置く。
表示名はTikTok側でいつでも変わるので、ファイル名も人の同定と同じく
ユーザー名(display_id)に揃える（cid かユーザー名以外では同定しない決まり）。
"""
import re

SUBDIR = "assets/avatars"
_UNSAFE = re.compile(r"[^a-z0-9._-]")


def av_key(user):
    """@や大文字のゆらぎを吸収したユーザー名キー。空なら ''。"""
    u = str(user or "").strip().lstrip("@").lower()
    return _UNSAFE.sub("", u)


def av_filename(user):
    k = av_key(user)
    return f"{k}.webp" if k else ""


def av_relpath(user):
    """ページから参照する相対パス（docs/ 起点）。"""
    f = av_filename(user)
    return f"{SUBDIR}/{f}" if f else ""
