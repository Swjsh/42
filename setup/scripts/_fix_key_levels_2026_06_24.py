"""One-shot pre-open repair of key-levels.json for 2026-06-24.

Cause: 06-23 was a dark day (usage cap) -> the EOD-06-23 role-flip never ran, and
today's premarket did only a light re-stamp. key-levels.json#levels[] still carries
the 06-22 regime (price 743.86) while SPY gapped down to ~736. Two concrete defects:
  (1) 743.35 still tagged type=support/role=double_confirmed_support, but SPY CLOSED
      ~734.97 on 6/23 (below it) -> it is now overhead RESISTANCE. level_reject only
      matches {resistance,transition,broken_to_resistance}, so the primary bear zone
      is untradeable as-is.
  (2) Today's near-price levels (PMH 737.11, PML 734.80, prior close 734.97) are absent
      -> no level-tie possible in the 734-738 zone, and the heartbeat cannot create them
      during RTH (protocol: only premarket/EOD create levels).

Fix (premarket-authority, market-closed, idempotent): flip 743.35 -> resistance, add the
three near-price levels (chart-verified prices from today-bias.json @ premarket 08:30 ET),
refresh header + append an audit entry. Atomic write + re-parse validation.
"""
import json, os, datetime

ROOT = r"C:\Users\jackw\Desktop\42"
KL = os.path.join(ROOT, "automation", "state", "key-levels.json")
TB = os.path.join(ROOT, "automation", "state", "today-bias.json")

with open(KL, "r", encoding="utf-8-sig") as f:
    kl = json.load(f)
with open(TB, "r", encoding="utf-8-sig") as f:
    tb = json.load(f)

TODAY = "2026-06-24"
NOW = "2026-06-24T08:42:00-04:00"
EOD = "2026-06-24T16:00:00-04:00"
spot = float(tb["premarket_context"]["current_price"])  # 736.97, chart-verified premarket

levels = kl["levels"]
by_price = {round(float(l["price"]), 2): l for l in levels}

changes = []

# (1) Flip 743.35 support -> resistance (broken_to_resistance) after 6/23 close below it
if 743.35 in by_price:
    lv = by_price[743.35]
    if lv.get("type") != "resistance" or lv.get("role") != "broken_to_resistance":
        lv["type"] = "resistance"
        lv["role"] = "broken_to_resistance"
        lv["broken_at"] = "2026-06-23T16:00:00-04:00"
        lv["verified_at"] = NOW
        lv["expires_at"] = "2026-06-30T16:00:00-04:00"
        lv["reasoning"] = ("Double-bottom support 6/18+6/22 BROKEN on 6/23 close (~734.97 << 743.35). "
                           "Role flipped support->resistance. First test from below = primary bear rejection zone today.")
        lv["notes"] = ("Role corrected 2026-06-24 pre-open: EOD-06-23 role-flip skipped (dark day, usage cap); "
                       "price closed below -> now overhead resistance. Was: support/double_confirmed_support.")
        changes.append("743.35 support->resistance (broken_to_resistance)")

# (2) Add today's near-price levels if absent
def ensure(price, label, ltype, role, tier, source, reasoning, expires, draw=True):
    p = round(price, 2)
    if p in by_price:
        return
    levels.append({
        "price": price, "type": ltype, "role": role, "label": label, "tier": tier,
        "source": source, "verified_at": NOW, "expires_at": expires,
        "reasoning": reasoning,
        "notes": "Added 2026-06-24 pre-open repair (premarket omitted; chart-verified premarket prices from today-bias.json).",
        "entity_id": None, "draw_needed": draw,
    })
    by_price[p] = levels[-1]
    changes.append(f"added {label} {price} ({ltype})")

ensure(737.11, "PMH_2026-06-24", "resistance", None, "Active",
       "5-min premarket high before 09:30 ET 2026-06-24",
       "Today's premarket high; first overhead test / bull breakout pivot. Bear rejection zone if ribbon flips bear.",
       EOD)
ensure(734.80, "PML_2026-06-24", "support", None, "Active",
       "5-min premarket low before 09:30 ET 2026-06-24",
       "Today's premarket low; intraday floor. 5m close below = bear acceleration / premarket low taken out.",
       EOD)
ensure(734.97, "PRIOR_CLOSE_2026-06-23", "support", None, "Reference",
       "1D bar 2026-06-23 RTH close ~734.97",
       "6/23 RTH close; near-price reference support and gap-fill anchor.",
       "2026-06-26T16:00:00-04:00", draw=False)

# (3) Header refresh + audit entry
kl["as_of"] = NOW
kl["for_session"] = TODAY
kl["date"] = TODAY
kl["spot_at_compute"] = spot
kl.setdefault("audit_log", []).append({
    "timestamp": NOW,
    "count_in": len(levels) - sum(1 for c in changes if c.startswith("added")),
    "count_pass": len(levels),
    "count_dropped": 0,
    "count_added": sum(1 for c in changes if c.startswith("added")),
    "tv_available": True,
    "note": ("PRE-OPEN REPAIR 2026-06-24 (interactive readiness review). Outage-induced staleness: "
             "6/23 dark -> EOD role-flip skipped + premarket light re-stamp. " + "; ".join(changes) + "."),
})

# Atomic write + re-parse validation
tmp = KL + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(kl, f, indent=2)
with open(tmp, "r", encoding="utf-8") as f:
    json.load(f)  # validates
os.replace(tmp, KL)

print("CHANGES:", changes if changes else "NONE (idempotent no-op)")
print("\nLEVELS NOW (price | type | role | tier | label):")
for l in sorted(kl["levels"], key=lambda x: -float(x["price"])):
    mark = "  <-- RESISTANCE above" if float(l["price"]) > spot else "  (support below)"
    print(f"  {float(l['price']):7.2f} | {l['type']:11} | {str(l.get('role')):22} | {l['tier']:9} | {l['label']}{mark if l['type'] in ('resistance','support') else ''}")
print(f"\nspot_at_compute={spot}  |  total levels={len(kl['levels'])}")
