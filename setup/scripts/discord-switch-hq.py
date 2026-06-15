"""One-shot: send hello to HQ #general and set it as default."""
import json
from pathlib import Path
import requests

CFG_PATH = Path(__file__).resolve().parents[2] / "automation" / "state" / ".discord-config.json"
HQ_GENERAL = "1484377912328192022"

config = json.loads(CFG_PATH.read_text(encoding="utf-8"))
token = config["bot_token"]
msg = (
    "**Gamma here -- this is the dedicated HQ server.**\n"
    "I also pinged #general in SwjshVault, but unless you tell me otherwise I'll use THIS channel "
    "for ongoing alerts to keep your main server clean.\n"
    "\n"
    "**Two-way bridge status:** sending works (you're reading this). Receiving (your replies -> me) "
    "is being built next -- a polling loop that checks for new messages every 15s and writes them to "
    "`automation/state/discord-inbox.jsonl` for the heartbeat to pick up.\n"
    "\n"
    "Reply with anything to confirm receipt and I'll switch over."
)
r = requests.post(
    f"https://discord.com/api/v10/channels/{HQ_GENERAL}/messages",
    headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
    json={"content": msg},
    timeout=15,
)
print("HQ #general POST:", r.status_code)
if r.status_code in (200, 201):
    config["channel_id"] = HQ_GENERAL
    config["channel_name_hint"] = "HQ #general (dedicated)"
    CFG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Saved HQ #general as default channel.")
else:
    print(r.text)
