#!/usr/bin/env python3
"""標準入力のテキストを #tiktoklive立ち上げ に投稿する。
pococha/.slack_token (xoxb Bot) を流用。<@U...> メンションで ito_sukeaki を通知。
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/Claude/pococha"))
import slack_notify  # noqa: E402

CHANNEL = "C0A8R10CBPE"  # #tiktoklive立ち上げ

def main():
    text = sys.stdin.read().rstrip()
    if not text:
        print("空メッセージのため送信しない", file=sys.stderr); return
    r = slack_notify.send_channel(CHANNEL, text)
    print("slack送信:", r, file=sys.stderr)

if __name__ == "__main__":
    main()
