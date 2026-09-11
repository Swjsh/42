<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=1.713s | action=audit-forager-fabrication-recurrence -->
<!-- reason: Two open worker_fabrication escalations (4x recurrence since 08-20) directly corrupt the analysis pipeline; forager is the natural role to investigate its own claim path, and this is the highest-leverage hygiene fix before any more contender work. -->

1. `queue.md` path checks:
* `analysis/recommendations/prereg-fleet-signal-unreadable-bundle-2026-09-29.md`: MISSING
* `analysis/recommendations/signal.json`: MISSING
* `analysis/recommendations/nlwb-pullback-reclaim-20260905-1453.txt`: MISSING

2. Literal filename grep: `analysis/recommendations/` returned 0 matches for all three files (directories containing them: none).

3. Vulnerability in `setup/hooks/forager_artifact_claim.py`: The validation logic checks metadata syntax and schema conformance, but lacks an `os.path.exists()` filesystem validation guard against the target artifacts at claim time.

4. Fix proposal:
* **Add filesystem check**: Insert `if not os.path.exists(path): raise FileNotFoundError(f"Claimed artifact {path} does not exist.")` directly inside the claim validation loop in `forager_artifact_claim.py`.
* **Structured stderr**: Ensure the exception catches and logs JSON-structured error payloads (`{"error": "artifact_missing", "path": path}`) to stderr before exiting with a non-zero status.
* **Queue rejection**: Hook the check into the escalation parser to automatically invalidate and reject pending queue items referencing missing paths.