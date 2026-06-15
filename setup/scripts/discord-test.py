"""One-shot Discord bot connectivity test.

Lists guilds the bot has joined and channels in each guild. If a guild has a
text channel, sends a hello message to the first one and updates the config
JSON with the discovered channel_id.

Usage:
    python setup/scripts/discord-test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "automation" / "state" / ".discord-config.json"
API = "https://discord.com/api/v10"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    token = config["bot_token"]

    print("=" * 60)
    print("Gamma Discord Bot Connectivity Test")
    print("=" * 60)

    # 1. Verify token works -- get bot's own user info.
    me = requests.get(f"{API}/users/@me", headers=auth_headers(token), timeout=15)
    if me.status_code != 200:
        print(f"FAIL: token rejected ({me.status_code}): {me.text}")
        return 1
    me_data = me.json()
    print(f"Bot user: {me_data['username']}#{me_data.get('discriminator', '0000')}")
    print(f"Bot ID:   {me_data['id']}")

    # 2. List guilds.
    guilds_resp = requests.get(f"{API}/users/@me/guilds", headers=auth_headers(token), timeout=15)
    if guilds_resp.status_code != 200:
        print(f"FAIL listing guilds ({guilds_resp.status_code}): {guilds_resp.text}")
        return 1
    guilds = guilds_resp.json()
    print(f"\nGuilds joined: {len(guilds)}")

    if not guilds:
        print()
        print("BOT NOT IN ANY SERVER YET.")
        print()
        print("Invite the bot to a server with this URL (paste in browser, log in, pick server):")
        client_id = config.get("client_id") or config.get("application_id")
        invite_url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={client_id}"
            f"&permissions=2048"  # Send Messages
            f"&scope=bot"
        )
        print(f"  {invite_url}")
        print()
        print("After inviting, re-run this script.")
        return 2

    # 3. For each guild, list text channels and try to send hello.
    sent = False
    for guild in guilds:
        print(f"\nGuild: {guild['name']} (id={guild['id']})")
        channels_resp = requests.get(
            f"{API}/guilds/{guild['id']}/channels",
            headers=auth_headers(token),
            timeout=15,
        )
        if channels_resp.status_code != 200:
            print(f"  cant list channels ({channels_resp.status_code}): {channels_resp.text}")
            continue
        channels = channels_resp.json()
        text_channels = [c for c in channels if c.get("type") == 0]  # 0 = GUILD_TEXT
        print(f"  text channels: {len(text_channels)}")
        for ch in text_channels[:5]:
            print(f"    - #{ch['name']} (id={ch['id']})")

        if text_channels and not sent:
            target = text_channels[0]
            msg = (
                "**Gamma -- Multi-Agent Gamma 2.0 online.**\n"
                "Reply here and I'll see your messages on next poll (15s).\n"
                "I'll DM you when:\n"
                "- Weekend research finishes (or fails)\n"
                "- v15 candidate is ready for review\n"
                "- Premarket / heartbeat / EOD hits a critical state (kill-switch, drift, etc.)\n"
                "- Anything blocks autonomous trading\n"
                "\n"
                "Currently: PHASE 0 of weekend autoresearch ~78% complete."
            )
            send_resp = requests.post(
                f"{API}/channels/{target['id']}/messages",
                headers=auth_headers(token),
                json={"content": msg},
                timeout=15,
            )
            if send_resp.status_code in (200, 201):
                print(f"\n  SENT hello to #{target['name']} (channel_id={target['id']})")
                # Save channel_id for the bridge.
                config["channel_id"] = target["id"]
                config["guild_id"] = guild["id"]
                CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
                print(f"  Saved channel_id to {CONFIG_PATH.name}")
                sent = True
            else:
                print(f"  FAIL sending to #{target['name']} ({send_resp.status_code}): {send_resp.text}")

    if not sent:
        print("\nNo text channel found to message. Bot is in guild(s) but no text channels available.")
        return 3

    print("\n" + "=" * 60)
    print("CONNECTIVITY OK -- check Discord for the hello message.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
