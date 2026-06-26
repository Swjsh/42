"use strict";

// Obligation registry checker for the Gamma companion.
//
// WHY THIS EXISTS: the rig owes itself daily obligations -- premarket ran, the
// EOD pipeline closed, the heartbeat is alive, scheduled tasks fired, the gym
// passed, watchers see a live feed. Without an explicit registry, a silently
// dead job looks identical to "all quiet" -- the FAIL-GREEN trap. This module
// reconciles each declared obligation in automation/state/obligations.json
// against the CONTENT freshness of its evidence file (mtime AND an internal
// timestamp/field), NOT mere file-existence, and returns a flat verdict array.
//
// CONTRACT (returned by checkObligations):
//   [ { id, label, ok, detail, severity } ]
//
// HARD RULES:
//   * NEVER throws. Any read/parse error degrades the affected obligation to
//     ok:false with an explanatory detail -- a checker that crashes is itself a
//     fail-green. A missing evidence file is a FAILED obligation, never a pass.
//   * Read-only. This module only reads state; it places no orders and edits
//     no production doctrine.

const fs = require("fs");
const path = require("path");

const REGISTRY_REL = ["automation", "state", "obligations.json"];

function readJSONSafe(p) {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function mtimeMs(p) {
  try {
    return fs.statSync(p).mtimeMs;
  } catch {
    return null;
  }
}

// ET (America/New_York) "today" as YYYY-MM-DD, DST-correct via Intl.
function etToday(now) {
  try {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    return fmt.format(now || new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

// Is the ET date a weekday (Mon-Fri)? Used for expect_on:"weekday" obligations
// so weekend "missing premarket" never red-flags.
function etIsWeekday(now) {
  try {
    const wd = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      weekday: "short",
    }).format(now || new Date());
    return !["Sat", "Sun"].includes(wd);
  } catch {
    const d = (now || new Date()).getUTCDay();
    return d !== 0 && d !== 6;
  }
}

function ageMinutes(tsMs, now) {
  if (tsMs == null) return null;
  return ((now || Date.now()) - tsMs) / 60000;
}

// Resolve {today} / {date} placeholders in an evidence path to the ET date.
function resolvePath(root, rel, today) {
  const filled = String(rel).replace(/\{today\}|\{date\}/g, today);
  return path.join(root, filled);
}

// Pull an internal timestamp from the evidence content into epoch-ms, honoring
// the declared field kind. Returns null when absent/unparseable so the caller
// can fall back to mtime (and flag the weaker signal in the detail).
function internalTsMs(content, ob) {
  if (!content || !ob.freshness_field) return null;
  const raw = content[ob.freshness_field];
  if (raw == null) return null;
  const kind = ob.freshness_field_kind || "iso";
  if (kind === "et_date") {
    // A bare YYYY-MM-DD (ET). Compare by date string, not epoch -- callers
    // handle that path separately; here we just signal "present".
    return null;
  }
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : null;
}

// Build the standard result object.
function result(ob, ok, detail) {
  return {
    id: ob.id,
    label: ob.label || ob.id,
    ok: !!ok,
    detail: detail || "",
    severity: ob.severity || "medium",
  };
}

// Evaluate one obligation. Pure, defensive, never throws.
function evalOne(root, ob, now) {
  const today = etToday(now);

  // Obligations only "due" on weekdays must not red-flag on weekends.
  if (ob.expect_on === "weekday" && !etIsWeekday(now)) {
    return result(ob, true, "not due (weekend) -- ET " + today);
  }

  const evPath = resolvePath(root, ob.expect_evidence, today);
  const exists = fs.existsSync(evPath);

  // FAIL-GREEN GUARD: a missing evidence file is a FAILED obligation.
  if (!exists) {
    return result(
      ob,
      false,
      "evidence missing: " + ob.expect_evidence.replace(/\{today\}|\{date\}/g, today) +
        (ob.detail_hint ? " | " + ob.detail_hint : "")
    );
  }

  // --- dated_file: existence-of-today's-file IS the freshness signal ---
  if (ob.evidence_kind === "dated_file") {
    const ageMin = ageMinutes(mtimeMs(evPath), now);
    if (ob.fresh_within != null && ageMin != null && ageMin > ob.fresh_within) {
      return result(
        ob,
        false,
        "today's file present but stale: mtime " + Math.round(ageMin) +
          "m old (> " + ob.fresh_within + "m)"
      );
    }
    return result(ob, true, "today's file present (" +
      (ageMin == null ? "?" : Math.round(ageMin)) + "m old)");
  }

  // --- everything else is JSON content we can introspect ---
  const content = readJSONSafe(evPath);
  if (content == null) {
    return result(ob, false, "evidence unreadable/corrupt JSON: " + evPath);
  }

  // et_date freshness: the internal date field must equal ET today.
  if (ob.freshness_field_kind === "et_date") {
    const v = content[ob.freshness_field];
    if (v !== today) {
      return result(
        ob,
        false,
        ob.freshness_field + "=" + JSON.stringify(v) + " != ET today " + today +
          " -- did not run today" + (ob.detail_hint ? " | " + ob.detail_hint : "")
      );
    }
    // Date matches today: passes the freshness gate. Fall through to any
    // verdict/subcheck gates below.
  } else {
    // timestamp freshness: prefer the internal field, fall back to mtime.
    let tsMs = internalTsMs(content, ob);
    let basis = "field " + (ob.freshness_field || "");
    if (tsMs == null) {
      tsMs = mtimeMs(evPath);
      basis = "mtime (field " + (ob.freshness_field || "?") + " absent)";
    }
    const ageMin = ageMinutes(tsMs, now);
    if (ob.fresh_within != null && ageMin != null && ageMin > ob.fresh_within) {
      return result(
        ob,
        false,
        "stale: " + Math.round(ageMin) + "m old via " + basis +
          " (> " + ob.fresh_within + "m) -- producer stopped updating" +
          (ob.detail_hint ? " | " + ob.detail_hint : "")
      );
    }
  }

  // --- top-level verdict gate (e.g. engine-health.verdict, audit.health) ---
  if (ob.verdict_field && Array.isArray(ob.verdict_red_values)) {
    const v = content[ob.verdict_field];
    if (ob.verdict_red_values.includes(v)) {
      return result(ob, false, ob.verdict_field + "=" + v + " (RED)" +
        (ob.detail_hint ? " | " + ob.detail_hint : ""));
    }
  }

  // --- numeric count gate (e.g. scheduled-tasks flags_count > 0) ---
  if (ob.count_field && typeof content[ob.count_field] === "number" &&
      typeof ob.count_red_above === "number") {
    const n = content[ob.count_field];
    if (n > ob.count_red_above) {
      return result(ob, false, ob.count_field + "=" + n +
        " (> " + ob.count_red_above + ")" +
        (ob.detail_hint ? " | " + ob.detail_hint : ""));
    }
  }

  // --- sub-check array gate (e.g. engine-health.checks[].status) ---
  if (ob.subcheck_array && Array.isArray(content[ob.subcheck_array])) {
    const arr = content[ob.subcheck_array];
    const redValue = ob.subcheck_red_value || "RED";
    const offenders = [];
    for (const c of arr) {
      if (!c || typeof c !== "object") continue;
      const name = c[ob.subcheck_name_field || "name"];
      // Restrict to a single named sub-check when declared.
      if (ob.subcheck_only_name && name !== ob.subcheck_only_name) continue;
      const status = c[ob.subcheck_status_field || "status"];
      if (status !== redValue) continue;
      // When a critical filter is declared, only critical reds fail.
      if (ob.subcheck_critical_field && !c[ob.subcheck_critical_field]) continue;
      offenders.push(name || "(unnamed)");
    }
    if (offenders.length) {
      return result(ob, false, "sub-check RED: " + offenders.join(", ") +
        (ob.detail_hint ? " | " + ob.detail_hint : ""));
    }
    // If we required a specific sub-check by name and it was absent entirely,
    // that is a fail-green risk -- the beacon isn't reporting what we expect.
    if (ob.subcheck_only_name) {
      const present = arr.some(
        (c) => c && c[ob.subcheck_name_field || "name"] === ob.subcheck_only_name
      );
      if (!present) {
        return result(ob, false, "expected sub-check '" + ob.subcheck_only_name +
          "' absent from " + ob.subcheck_array);
      }
    }
  }

  return result(ob, true, "ok (fresh, no RED signals)");
}

// Public API. Reads the registry, evaluates every obligation, returns the flat
// verdict array. Never throws: a missing/corrupt registry yields one synthetic
// failed obligation so the companion still surfaces the problem.
function checkObligations(root, nowMs) {
  const now = typeof nowMs === "number" ? nowMs : Date.now();
  try {
    const reg = readJSONSafe(path.join(root, ...REGISTRY_REL));
    if (!reg || !Array.isArray(reg.obligations)) {
      return [
        {
          id: "registry",
          label: "Obligation registry",
          ok: false,
          detail: "automation/state/obligations.json missing or malformed",
          severity: "high",
        },
      ];
    }
    return reg.obligations.map((ob) => {
      try {
        return evalOne(root, ob, now);
      } catch (e) {
        // A single broken obligation must not take down the whole check.
        return {
          id: (ob && ob.id) || "unknown",
          label: (ob && ob.label) || "unknown obligation",
          ok: false,
          detail: "checker error: " + (e && e.message ? e.message : String(e)),
          severity: (ob && ob.severity) || "medium",
        };
      }
    });
  } catch (e) {
    return [
      {
        id: "registry",
        label: "Obligation registry",
        ok: false,
        detail: "checkObligations failed: " + (e && e.message ? e.message : String(e)),
        severity: "high",
      },
    ];
  }
}

module.exports = { checkObligations };
