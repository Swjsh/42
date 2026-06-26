# Plan A — Two More Free Shadow Evaluators

**Date:** 2026-06-24  
**Status:** ACTIVE — building now  
**Companion:** [`FREE-AGENT-PLAN-B-KITCHEN.md`](FREE-AGENT-PLAN-B-KITCHEN.md)

---

## What we already have

Nemotron v11.0 scored 27/27 DTs = 100% across 4 trading days using the iron-gate hardening approach:

1. Pick a free model on OpenRouter
2. Wrap it in a single markdown rubric file
3. Replay `decisions.jsonl` — find every hallucination
4. Add a rule to the rubric → retest → repeat
5. Ship when DT agreement ≥ 85%

Full details: [`analysis/shadow-model/PROMOTION-SCORECARD.md`](../../analysis/shadow-model/PROMOTION-SCORECARD.md)  
Evaluator script: `setup/scripts/shadow_model_eval.py` (v11.0)  
Daily auto-scorer: `Gamma_ShadowEval` (16:05 ET weekdays)

---

## Two new models

| Model ID | Params | Context | Notes |
|---|---|---|---|
| `qwen/qwen3.6-plus:free` | 235B MoE (22B active) | 1M | Fast, strong structured output, function calling |
| `deepseek/deepseek-r1:free` | ~64B | 64K | Reasoning model — outputs `<think>...</think>` before JSON. Temperature must be 0.6. Reasoning traces are useful for debugging. |

---

## What gets built

### 1. External rubric files in `setup/rubrics/`

Move `RUBRIC_SYSTEM_PROMPT` out of `shadow_model_eval.py` into:

```
setup/rubrics/
  nemotron.md      ← extracted from shadow_model_eval.py (source of truth moves here)
  qwen.md          ← starts as nemotron.md copy, hardens iteratively
  deepseek-r1.md   ← same + extra rule: "ignore your <think> reasoning if it contradicts rubric thresholds"
```

Each file has a `## Failures` section at the bottom that grows as hallucinations are found and rules are added.

### 2. `--model` flag in `shadow_model_eval.py`

```
python shadow_model_eval.py --date 2026-06-24 --account both --model nemotron
python shadow_model_eval.py --date 2026-06-24 --account both --model qwen
python shadow_model_eval.py --date 2026-06-24 --account both --model deepseek-r1
```

Model configs in a `MODELS` dict at the top:

```python
MODELS = {
    "nemotron": {
        "id": "nvidia/nemotron-3-super-120b-a12b:free",
        "rubric_file": "setup/rubrics/nemotron.md",
        "temperature": 0.0,
        "max_tokens": 4096,
    },
    "qwen": {
        "id": "qwen/qwen3.6-plus:free",
        "rubric_file": "setup/rubrics/qwen.md",
        "temperature": 0.0,
        "max_tokens": 4096,
    },
    "deepseek-r1": {
        "id": "deepseek/deepseek-r1:free",
        "rubric_file": "setup/rubrics/deepseek-r1.md",
        "temperature": 0.6,
        "max_tokens": 8192,
        "strip_think_tags": True,
    },
}
```

### 3. Per-model scorecard directories

```
analysis/shadow-model/
  nemotron/
    PROMOTION-SCORECARD.md   ← existing file moves here
    2026-05-07-scorecard.md
    ...
  qwen/
    PROMOTION-SCORECARD.md   ← new
    ...
  deepseek-r1/
    PROMOTION-SCORECARD.md   ← new
    ...
```

### 4. Ensemble vote in `Gamma_ShadowEval`

After all 3 models run, `run-shadow-eval.ps1` generates an ensemble report:
- 2-of-3 majority vote per tick → ensemble agreement with Haiku
- Flag ticks where all 3 disagree with Haiku → strong signal Haiku made an unusual call

---

## DeepSeek-R1 special handling

1. Strip `<think>...</think>` block before JSON parsing (everything before first `{`)
2. Save the thinking trace to a separate field in the scorecard (useful for debugging)
3. Iron-gate rule added to `deepseek-r1.md`: "If any rubric threshold (M1/M2/M3/T0) applies, output the rubric decision directly. Do not reason around it."
4. Temperature = 0.6 is non-negotiable — 0.0 breaks R1's chain-of-thought

---

## Hardening process (per model)

1. Cold run on all 4 existing dates
2. Log every DT miss — catalog the hallucination type
3. Add one rubric rule per miss class
4. Re-run until ≥ 85% DT agreement
5. Document the model's "personality" (what it gets wrong that Nemotron doesn't)

---

## Success criteria

- Each model: ≥ 85% DT agreement on ≥ 4 test dates
- Zero unrecovered PARSE_ERRORs per model
- Zero vocab violations after rubric hardening
- Ensemble (2-of-3): target ≥ 92% DT agreement with Haiku

---

## Order of operations

1. Extract `RUBRIC_SYSTEM_PROMPT` → `setup/rubrics/nemotron.md`
2. Add `--model` flag + `MODELS` dict to `shadow_model_eval.py`
3. Create `setup/rubrics/qwen.md` (copy of nemotron.md + Qwen header)
4. Create `setup/rubrics/deepseek-r1.md` (copy + think-tag rule)
5. Cold run Qwen on 4 dates → log misses → harden → retest
6. Cold run DeepSeek-R1 on 4 dates → log misses → harden → retest
7. Wire ensemble report into `run-shadow-eval.ps1`
8. Move `analysis/shadow-model/` into per-model subdirectories
