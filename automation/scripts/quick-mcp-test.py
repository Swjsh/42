import json
import requests
import os
from datetime import datetime, timezone

# Quick test: hit CDP to verify TV is responding
try:
    resp = requests.get("http://localhost:9222/json/version", timeout=2)
    if resp.status_code == 200:
        print("TV_OK")
    else:
        print(f"TV_ERROR: {resp.status_code}")
except Exception as e:
    print(f"TV_DOWN: {str(e)[:20]}")
