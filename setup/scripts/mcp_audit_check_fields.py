import json
from pathlib import Path
import urllib.request

mcp_path = Path(r"C:\Users\jackw\Desktop\42\.mcp.json")
data = json.loads(mcp_path.read_text())
safe_env = data.get("mcpServers", {}).get("alpaca", {}).get("env", {})

key = safe_env.get("ALPACA_API_KEY")
secret = safe_env.get("ALPACA_SECRET_KEY")
base_url = safe_env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

headers = {
    "APCA-API-KEY-ID": key,
    "APCA-API-SECRET-KEY": secret,
    "Content-Type": "application/json"
}

req = urllib.request.Request(f"{base_url}/v2/account", headers=headers)
with urllib.request.urlopen(req, timeout=5) as resp:
    resp_data = json.loads(resp.read())
    print(json.dumps(resp_data, indent=2))
