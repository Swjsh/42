"""study_curriculum.py -- deterministic, $0 helper for the GAMMA-STUDY-CURRICULUM

standing conductor mode (automation/overnight/queue.md GAMMA-STUDY-CURRICULUM, MED,
filed 2026-07-22 night). Read markdown/doctrine/STUDY-CURRICULUM.md for the doctrine
context.

Purpose: keep the LLM STUDY-mode fire (automation/prompts/conductor.md MODES) doing
ONLY the reading/distilling. Everything mechanical -- picking the least-recently-studied
topic, appending the 10-line note, stamping the date -- is deterministic Python, $0,
no LLM call, no network beyond the (optional) `verify-sources` health check.

STUDY-CURRICULUM.md's shape is fixed by this module (see its own header note: "never
hand-edit this column, the parser expects the exact table shape"):

  | Topic | Slug | Sources | Last Studied (ET) | Status |
  |---|---|---|---|---|
  | <name> | <slug> | <n> | <YYYY-MM-DD or "never"> | <status> |

  ## Sources
  ### <slug> -- <name>
  - <url> (<code>, verified <date>[ -- <note>])
  ...

  ## Study notes
  ### <slug> -- <name>
  _none yet -- filed by the conductor STUDY-mode fire._
  #### <YYYY-MM-DD> (ET)
  1. ...
  ...
  10. ...

Usage:
  python study_curriculum.py next-topic [--curriculum PATH] [--now ISO8601] [--json]
  python study_curriculum.py record --topic SLUG --note-file PATH [--curriculum PATH] [--now ISO8601]
  python study_curriculum.py verify-sources [--curriculum PATH] [--topic SLUG]

Exit codes:
  next-topic : 0 on success (always finds a topic -- the table is never empty in
               practice; 1 if the curriculum file has zero topics, which should not
               happen outside a broken doc).
  record     : 0 on success, 2 on a malformed note file (not exactly 10 non-blank
               lines) or unknown --topic slug.
  verify-sources: 0 always (a dead source is reported, not a failure -- this is a
               diagnostic, not a gate).
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover -- py<3.9 not used in this repo's venvs
    ZoneInfo = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CURRICULUM = REPO_ROOT / "markdown" / "doctrine" / "STUDY-CURRICULUM.md"
ET_ZONE = ZoneInfo("America/New_York") if ZoneInfo else timezone.utc

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gamma-research/1.0"

TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<slug>[A-Za-z0-9_]+)\s*\|\s*(?P<sources>\d+)\s*\|"
    r"\s*(?P<last>never|\d{4}-\d{2}-\d{2})\s*\|\s*(?P<status>[^|]+?)\s*\|\s*$"
)
SOURCE_HEADER_RE = re.compile(r"^###\s+(?P<slug>[A-Za-z0-9_]+)\s+--\s+(?P<name>.+)$")
SOURCE_LINE_RE = re.compile(r"^-\s+(?P<url>\S+)\s+\((?P<meta>.+)\)\s*$")


class CurriculumError(Exception):
    """Raised for a malformed STUDY-CURRICULUM.md -- fail loudly, never guess."""


def now_et(now_override: str | None = None) -> datetime:
    if now_override:
        dt = datetime.fromisoformat(now_override)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET_ZONE)
        return dt.astimezone(ET_ZONE)
    return datetime.now(timezone.utc).astimezone(ET_ZONE)


# --------------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------------- #
def parse_table(text: str) -> list[dict]:
    """Return one dict per topic row, in table order. Raises CurriculumError if the
    table is missing or empty -- a broken/empty curriculum is a loud failure, not a
    silent "no topics found"."""
    rows: list[dict] = []
    for line in text.splitlines():
        m = TABLE_ROW_RE.match(line)
        if m:
            rows.append(
                {
                    "name": m.group("name"),
                    "slug": m.group("slug"),
                    "sources": int(m.group("sources")),
                    "last_studied": m.group("last"),
                    "status": m.group("status"),
                }
            )
    if not rows:
        raise CurriculumError(
            "no topic rows matched the expected table shape in STUDY-CURRICULUM.md "
            "-- table format changed or file is empty; fix the doc, don't guess."
        )
    return rows


def parse_sources(text: str) -> dict[str, list[dict]]:
    """slug -> list of {url, meta} under the '## Sources' section."""
    lines = text.splitlines()
    sources: dict[str, list[dict]] = {}
    current_slug: str | None = None
    in_sources_section = False
    for line in lines:
        if line.strip() == "## Sources":
            in_sources_section = True
            continue
        if line.startswith("## ") and line.strip() != "## Sources":
            in_sources_section = False
            current_slug = None
            continue
        if not in_sources_section:
            continue
        hm = SOURCE_HEADER_RE.match(line)
        if hm:
            current_slug = hm.group("slug")
            sources[current_slug] = []
            continue
        sm = SOURCE_LINE_RE.match(line)
        if sm and current_slug:
            sources[current_slug].append({"url": sm.group("url"), "meta": sm.group("meta")})
    return sources


def pick_next_topic(rows: list[dict]) -> dict:
    """Least-recently-studied wins. 'never' sorts before any ISO date (never-studied
    topics are strictly more overdue than any studied one). Ties broken by table
    order (stable sort) so the rotation is deterministic run-to-run."""

    def sort_key(row: dict) -> tuple:
        if row["last_studied"] == "never":
            return (0, "")
        return (1, row["last_studied"])

    ranked = sorted(enumerate(rows), key=lambda pair: (sort_key(pair[1]), pair[0]))
    return ranked[0][1]


# --------------------------------------------------------------------------------- #
# next-topic
# --------------------------------------------------------------------------------- #
def cmd_next_topic(args: argparse.Namespace) -> int:
    curriculum_path = Path(args.curriculum)
    text = curriculum_path.read_text(encoding="utf-8")
    rows = parse_table(text)
    sources_by_slug = parse_sources(text)
    topic = pick_next_topic(rows)
    slug = topic["slug"]
    urls = sources_by_slug.get(slug, [])

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "slug": slug,
                    "name": topic["name"],
                    "last_studied": topic["last_studied"],
                    "sources": urls,
                }
            )
        )
        return 0

    print(f"TOPIC {slug} -- {topic['name']} (last studied: {topic['last_studied']})")
    if not urls:
        print("  (no sources found under '## Sources' for this slug -- check the doc)")
    for src in urls:
        print(f"  - {src['url']} ({src['meta']})")
    return 0


# --------------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------------- #
def _validate_note_lines(note_text: str) -> list[str]:
    """A study note is exactly 10 non-blank lines. Reject anything else loudly --
    a truncated or bloated note is a sign the LLM step skipped distillation."""
    lines = [ln for ln in note_text.splitlines() if ln.strip()]
    if len(lines) != 10:
        raise CurriculumError(
            f"note file must contain exactly 10 non-blank lines, found {len(lines)}"
        )
    return lines


def _update_table_last_studied(text: str, slug: str, date_str: str) -> str:
    out_lines = []
    updated = False
    for line in text.splitlines(keepends=False):
        m = TABLE_ROW_RE.match(line)
        if m and m.group("slug") == slug:
            new_line = (
                f"| {m.group('name')} | {slug} | {m.group('sources')} | "
                f"{date_str} | studied |"
            )
            out_lines.append(new_line)
            updated = True
        else:
            out_lines.append(line)
    if not updated:
        raise CurriculumError(f"no table row found for slug '{slug}' -- unknown topic")
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


def _append_note_block(text: str, slug: str, date_str: str, note_lines: list[str]) -> str:
    lines = text.splitlines(keepends=False)
    header_idx = None
    for i, line in enumerate(lines):
        hm = SOURCE_HEADER_RE.match(line)
        if hm and hm.group("slug") == slug:
            # only match headers that appear AFTER '## Study notes', not '## Sources'
            preceding = "\n".join(lines[:i])
            if "## Study notes" in preceding and preceding.rindex(
                "## Study notes"
            ) > preceding.rfind("## Sources"):
                header_idx = i
                break
    if header_idx is None:
        raise CurriculumError(
            f"no '## Study notes' entry found for slug '{slug}' -- unknown topic"
        )

    # find the end of this topic's block: next '### ' or '## ' header, or EOF
    end_idx = len(lines)
    for j in range(header_idx + 1, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end_idx = j
            break

    block = lines[header_idx:end_idx]
    # strip a lone "_none yet ...imeout" placeholder line if present (first real note)
    block = [ln for ln in block if not ln.strip().startswith("_none yet")]
    # trim trailing blank lines inside the block before appending
    while block and block[-1].strip() == "":
        block.pop()

    numbered = [
        ln if re.match(r"^\d+\.\s", ln) else f"{i + 1}. {ln}"
        for i, ln in enumerate(note_lines)
    ]
    new_block = block + [""] + [f"#### {date_str} (ET)"] + numbered
    # blank line separator before the next section
    new_block.append("")

    new_lines = lines[:header_idx] + new_block + lines[end_idx:]
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")


def cmd_record(args: argparse.Namespace) -> int:
    curriculum_path = Path(args.curriculum)
    note_path = Path(args.note_file)
    if not note_path.exists():
        print(f"ERROR: note file not found: {note_path}", file=sys.stderr)
        return 2

    text = curriculum_path.read_text(encoding="utf-8")
    rows = parse_table(text)
    slugs = {r["slug"] for r in rows}
    if args.topic not in slugs:
        print(f"ERROR: unknown topic slug '{args.topic}' -- known: {sorted(slugs)}", file=sys.stderr)
        return 2

    try:
        note_lines = _validate_note_lines(note_path.read_text(encoding="utf-8"))
    except CurriculumError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    date_str = now_et(args.now).strftime("%Y-%m-%d")

    try:
        text = _update_table_last_studied(text, args.topic, date_str)
        text = _append_note_block(text, args.topic, date_str, note_lines)
    except CurriculumError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    curriculum_path.write_text(text, encoding="utf-8")
    print(f"RECORDED {args.topic} -- {date_str} ({len(note_lines)} lines) -> {curriculum_path}")
    return 0


# --------------------------------------------------------------------------------- #
# verify-sources ($0 diagnostic -- GET, quote status codes)
# --------------------------------------------------------------------------------- #
def _fetch_status(url: str, timeout: float = 15.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:  # noqa: BLE001 -- diagnostic, report the class not silently pass
        return f"ERR:{type(e).__name__}"


def cmd_verify_sources(args: argparse.Namespace) -> int:
    curriculum_path = Path(args.curriculum)
    text = curriculum_path.read_text(encoding="utf-8")
    sources_by_slug = parse_sources(text)
    targets = (
        {args.topic: sources_by_slug.get(args.topic, [])}
        if args.topic
        else sources_by_slug
    )
    if args.topic and args.topic not in sources_by_slug:
        print(f"ERROR: unknown topic slug '{args.topic}'", file=sys.stderr)
        return 2
    for slug, urls in targets.items():
        for src in urls:
            status = _fetch_status(src["url"])
            print(f"{slug}\t{status}\t{src['url']}")
    return 0


# --------------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_next = sub.add_parser("next-topic", help="print the least-recently-studied topic + sources")
    p_next.add_argument("--curriculum", default=str(DEFAULT_CURRICULUM))
    p_next.add_argument("--now", default=None, help="ISO-8601 override, for tests")
    p_next.add_argument("--json", action="store_true")

    p_record = sub.add_parser("record", help="append a 10-line study note + stamp the date")
    p_record.add_argument("--topic", required=True, help="topic slug (see table)")
    p_record.add_argument("--note-file", required=True, help="path to a file with exactly 10 non-blank lines")
    p_record.add_argument("--curriculum", default=str(DEFAULT_CURRICULUM))
    p_record.add_argument("--now", default=None, help="ISO-8601 override, for tests")

    p_verify = sub.add_parser("verify-sources", help="$0 GET health check on every source URL")
    p_verify.add_argument("--curriculum", default=str(DEFAULT_CURRICULUM))
    p_verify.add_argument("--topic", default=None, help="limit to one topic slug")

    args = parser.parse_args(argv)

    if args.command == "next-topic":
        return cmd_next_topic(args)
    if args.command == "record":
        return cmd_record(args)
    if args.command == "verify-sources":
        return cmd_verify_sources(args)
    return 2  # unreachable -- argparse `required=True` rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
