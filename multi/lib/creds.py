"""Credential resolution for the multi-symbol lane — BY REFERENCE, never by copy.

The lane trades account PA38EG1JTFBT, which already has a provisioned key living in
`automation/state/crypto-twin/secrets.json`. Rather than copy that secret into a second file
(two places to rotate, two places to leak), `params.json` names a `key_source` and this module
dereferences it at runtime.

Consequences, stated because they are load-bearing:

* Rotating the key updates ONE file and both consumers pick it up.
* No secret value is ever written by this lane, printed, or logged. `masked()` exists for
  diagnostics and is the only thing that may touch a key in output.
* The account is SHARED with the crypto twin. That is a deliberate, J-directed choice
  (2026-08-19) after the alternative was raised. Its consequence is enforced in code:
  `equity_option_positions()` filters to OCC-shaped option symbols so this lane can never see,
  count, or close the twin's BTC position — and the twin's own crypto flat-check is
  correspondingly blind to these options. Neither program can flatten the other.
* Because both programs share one equity curve, ACCOUNT EQUITY IS NOT EVIDENCE for either.
  Each program's own ledger is its evidence. Anything that reads `equity` for attribution is
  wrong by construction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO_ROOT / "automation" / "state" / "multi" / "params.json"

# Named credential sources. Adding one is a deliberate act, not a string the caller supplies --
# this dict is the allowlist of files this lane may dereference.
_KEY_SOURCES: dict[str, tuple[Path, str]] = {
    "crypto-twin": (
        REPO_ROOT / "automation" / "state" / "crypto-twin" / "secrets.json",
        "twin",
    ),
}


class MultiCreds(NamedTuple):
    key: str
    secret: str
    base_url: str
    account_number: str
    source: str  # provenance for diagnostics -- never the value


class CredError(RuntimeError):
    """Raised loudly. A lane that cannot resolve credentials must never fall back to a
    different account by accident -- that is how orders land somewhere they were not meant to."""


def load_params(path: Path | None = None) -> dict:
    p = path or PARAMS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CredError(f"cannot read multi-lane params at {p}: {e}") from e


def resolve(params: dict | None = None) -> MultiCreds:
    """Dereference `params.account.key_source` into live credentials."""
    p = params if params is not None else load_params()
    acct = p.get("account")
    if not isinstance(acct, dict):
        raise CredError("multi params.json is missing its 'account' block")

    source = acct.get("key_source")
    expected_number = acct.get("account_number")
    if source not in _KEY_SOURCES:
        raise CredError(
            f"unknown key_source {source!r}; allowed: {sorted(_KEY_SOURCES)}. "
            f"Add it to _KEY_SOURCES deliberately rather than passing an arbitrary path."
        )

    secrets_path, arm = _KEY_SOURCES[source]
    if not secrets_path.exists():
        raise CredError(
            f"key_source {source!r} points at {secrets_path}, which does not exist. "
            f"Refusing to continue -- this lane must never silently fall through to another account."
        )
    try:
        doc = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CredError(f"cannot read {secrets_path}: {e}") from e

    entry = (doc.get("accounts") or {}).get(arm)
    if not isinstance(entry, dict):
        raise CredError(f"{secrets_path} has no accounts.{arm} entry")

    key = entry.get("key") or entry.get("api_key")
    secret = entry.get("secret") or entry.get("api_secret")
    base_url = (entry.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
    if not key or not secret:
        raise CredError(f"accounts.{arm} in {secrets_path} is missing key/secret")

    if "paper" not in base_url:
        raise CredError(
            f"multi lane resolved a NON-PAPER base_url ({base_url}). This lane is shadow/paper "
            f"only; arming live money is a J decision (OP-0 #1) and is not reachable from here."
        )

    return MultiCreds(
        key=key, secret=secret, base_url=base_url,
        account_number=str(expected_number or ""), source=f"{secrets_path.name}:{arm}",
    )


def masked(value: str) -> str:
    """First 4 chars + length. The only function here permitted to touch a key in output."""
    return f"{value[:4]}...(len={len(value)})" if value else "<empty>"


def verify_account(creds: MultiCreds | None = None) -> dict:
    """Read-only probe confirming the resolved key really points at the EXPECTED account.

    A key that silently resolves to a different account than params claims is the single worst
    failure this module could permit, so it is checked explicitly rather than assumed.
    """
    import json as _json
    from urllib.request import Request, urlopen

    c = creds or resolve()
    req = Request(
        f"{c.base_url}/v2/account",
        headers={"APCA-API-KEY-ID": c.key, "APCA-API-SECRET-KEY": c.secret},
    )
    with urlopen(req, timeout=25) as resp:  # noqa: S310 -- fixed https host
        acct = _json.loads(resp.read())

    got = str(acct.get("account_number") or "")
    if c.account_number and got != c.account_number:
        raise CredError(
            f"ACCOUNT MISMATCH: params.json says {c.account_number} but the resolved key "
            f"authenticates as {got}. Refusing to proceed -- orders would land on the wrong account."
        )
    return acct


if __name__ == "__main__":
    c = resolve()
    a = verify_account(c)
    print(f"source={c.source} key={masked(c.key)}")
    print(f"account={a.get('account_number')} equity={a.get('equity')} "
          f"options_level={a.get('options_approved_level')} status={a.get('status')}")
