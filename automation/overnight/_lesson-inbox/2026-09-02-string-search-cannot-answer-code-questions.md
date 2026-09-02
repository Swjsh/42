# Three times in one session, a substring search was asked a question only a parser can answer

**Date:** 2026-09-02 (Opus session, executing `markdown/planning/OPUS-WORK-ORDER-2026-09.md`)
**Theme:** C7 / guard-quality — a test that greps source is testing the documentation

## Symptom

Three separate guards written the same night failed, or nearly passed wrongly, for the same
reason: each used `in`, `.count()` or `re.findall` on source text to ask a question about
*code structure*, and prose in a docstring answered instead.

| guard | what it asked | what answered |
|---|---|---|
| `test_dms_dry_rehearsal` | "is there exactly ONE call to `close_all_spy_options`?" | the module docstring's sentence *"FLATTEN via `fleet_broker.close_all_spy_options` (the same primitive…)"* — reported 2 call sites, failed on its own false positive |
| `test_early_close_dry_run` | "does the `if DRY:` return come BEFORE the order call?" | `src.index("fleet_broker.close_all_spy_options(")` found the docstring at **char 476**, the real call is at **~14,000** — concluded the order path ran FIRST, which is the opposite of the truth |
| `test_fee_recalibration` | "does this module ever WRITE `FEE_RATES`?" | a dozen legitimate **reads** (`FEE_RATES["occ_per_contract"]`) — failed on the module's own correct code |

Two of the three failed loudly, which is the good outcome. The middle one is the dangerous
shape: it would have asserted a **safety property backwards** — "the dry-run guard precedes
the only order path" — and passed or failed for reasons unrelated to the property. A guard
that protects a broker-mutating call is exactly the guard that must not be approximate.

## Root cause

Source text contains at least three languages: code, comments, and docstrings. A substring
search reads all three as one. Every question of the form *"where is the call"*, *"how many
call sites"*, *"does A come before B"*, *"is this name assigned or only read"* is a question
about the **parse tree**, and the parse tree is the only thing that can answer it. Asking the
text gets you an answer about the documentation — and documentation deliberately names the
functions it describes, so the false positives cluster precisely where the guard matters.

## The rule

**If the assertion is about code structure, use `ast`. If it is about wording, use a string.**

```python
# WRONG -- "where is the call"
assert src.index("if DRY:") < src.index("fleet_broker.close_all_spy_options(")

# RIGHT -- ask the parser
tree = ast.parse(src)
calls = [n.lineno for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and n.func.attr == "close_all_spy_options"]
guards = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "DRY"]
assert min(guards) < calls[0]
```

Questions that are ALWAYS AST questions: how many call sites · does A precede B · is this
name written or only read · is this branch reachable before that statement · what arguments
does this call actually pass.

Questions a string search still answers fine: is the disclaimer present · does the log line
carry this marker · is this doc reference still spelled correctly.

## Why it recurred three times in one night

Because the string version *works* on the first example you try, and the failure mode is
silent until a docstring happens to name the symbol. Every one of these three modules has a
carefully-written docstring that names its own primitives — which is good practice, and it is
exactly what breaks the naive guard. The better the documentation, the more likely the grep
lies.

## Guards shipped

`backtest/tests/test_early_close_dry_run_2026_09_02.py` and
`test_fee_recalibration_2026_09_02.py` both now use `ast.walk`, and each carries a comment
naming this failure so the next editor does not "simplify" it back to a substring check.
`test_dms_dry_rehearsal_2026_09_02.py` strips comment lines before counting, which is the
weaker fix and should be upgraded to AST when next touched.

Related: [[2026-09-02-state-ready-is-not-it-ran]] (same session, same family — a check that
reads the wrong thing reports on the wrong thing).
