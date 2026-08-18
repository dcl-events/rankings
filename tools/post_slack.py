#!/usr/bin/env python3
"""標準入力のテキストを #tiktoklive立ち上げ に投稿する。

投稿主の優先順位:
  1) ユーザートークン  event-rankings/.slack_user_token (xoxp-...) があれば
     → ito_sukeaki 本人として投稿（chat:write）
  2) 無ければ Bot (pococha/.slack_token, xoxb) にフォールバック
     → pococha_event として投稿（要 /invite @pococha_event）
どちらも本文中の <@U0A6WU3P3LL> で ito_sukeaki をメンション。
"""
import sys, os, json, urllib.request

CHANNEL = "C0A8R10CBPE"  # #tiktoklive立ち上げ
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_TOKEN_FILE = os.path.join(REPO, ".slack_user_token")  # xoxp-... (chmod 600, gitignore)


def _post(token, channel, text):
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    text = sys.stdin.read().rstrip()
    if not text:
        print("空メッセージのため送信しない", file=sys.stderr); return
    if os.path.exists(USER_TOKEN_FILE):
        token = open(USER_TOKEN_FILE).read().strip()
        res = _post(token, CHANNEL, text)
        who = "ユーザー(ito_sukeaki)"
    else:
        sys.path.insert(0, os.path.expanduser("~/Claude/pococha"))
        import slack_notify  # noqa: E402
        res = slack_notify.send_channel(CHANNEL, text)
        who = "Bot(pococha_event)"
        res = res if isinstance(res, dict) else {"ok": bool(res)}
    if not res.get("ok"):
        print(f"slack失敗({who}):", res.get("error"), file=sys.stderr); sys.exit(1)
    print(f"slack送信OK({who})", file=sys.stderr)


if __name__ == "__main__":
    main()
