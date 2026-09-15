// HQ-TRADE-MOMENTS (2026-09-15): pure derivation of "a real fill just
// happened" events from fills-ledger.jsonl rows + their FIFO-matched
// closed-round-trip counterparts (lib/hq-positions-pure.ts#computeClosedToday)
// -- the world's own trade-moment mechanism J asked for: "the world visibly
// REACTS to real trade events." Event identity is the fill's OWN
// activity_id (never a synthetic client-side counter), so a bubble/ticker
// line fires exactly once per real fill and the active window is derived
// from the fill's real ts_et vs "now", never client-side memory -- a page
// reload inside the window still shows it, a reload after the window
// doesn't, and nothing repeats. Zero fs/Date.now() calls (pure, node
// --test-able); the adapter supplies "now" explicitly.

import type { ClosedPosition, FillRow } from "./hq-positions-pure";
import { shortStrikeLabel } from "./hq-positions-pure";

export type TradeMomentKind = "ENTER" | "EXIT";

/** One real fill turned into a world event. `activityId` is the fills-ledger
 * row's own id -- the caller (Scene.tsx/Hud.tsx) keys React lists and
 * "already shown" bookkeeping off this, never off array index or a
 * generated id. */
export interface TradeMomentEvent {
  activityId: string;
  arm: string;
  kind: TradeMomentKind;
  symbol: string;
  qty: number;
  price: number;
  tsEt: string;
  /** Realized $ for this fill's own round trip(s) -- null for an ENTER (no
   * realized P&L exists yet), a real signed number for an EXIT. */
  realizedUsd: number | null;
}

/** OCC symbol -> "put"/"call"/"" for the bubble/ticker copy ("ENTER put
 * 3x P757 @1.08"). Falls back to "" (never guesses) on an unparseable
 * symbol -- the caller still gets a usable line, just without the C/P word. */
function sideWord(symbol: string): string {
  const m = /^[A-Z]+\d{6}([CP])\d{8}$/.exec(symbol);
  if (!m) return "";
  return m[1] === "C" ? "call" : "put";
}

/** Short strike label ("P757") if parseable, else the raw symbol -- same
 * fallback rule hq-positions-pure.ts's own formatPositionClause uses. */
function strikeLabel(symbol: string): string {
  return shortStrikeLabel(symbol) ?? symbol;
}

/** One-line copy for the Pilot bubble / HUD ticker -- "safe-2 ENTER put 3x
 * P757 @1.08" / "bold-2 EXIT @0.62 +$75". Signed realized $ (never a bare
 * magnitude -- a losing exit must read as a loss, not a neutral number). */
export function formatTradeMomentLine(ev: TradeMomentEvent): string {
  const strike = strikeLabel(ev.symbol);
  if (ev.kind === "ENTER") {
    const word = sideWord(ev.symbol);
    return `${ev.arm} ENTER${word ? ` ${word}` : ""} ${ev.qty}x ${strike} @${ev.price.toFixed(2)}`;
  }
  const pnlTxt = ev.realizedUsd !== null
    ? ` ${ev.realizedUsd >= 0 ? "+" : "-"}$${Math.abs(Math.round(ev.realizedUsd))}`
    : "";
  return `${ev.arm} EXIT @${ev.price.toFixed(2)}${pnlTxt}`;
}

/** Builds one TradeMomentEvent per real fill row: every "buy" fill is an
 * ENTER; every "sell" fill is an EXIT, its realizedUsd summed from every
 * ClosedPosition row that shares its own exitActivityId (a single sell fill
 * can FIFO-split across multiple buy lots -- see computeClosedToday's own
 * partial-TP1 test -- all those splits collapse back into ONE event here,
 * matching "one bubble per fill", not "one bubble per FIFO split"). A sell
 * fill with no matching closed row (a cross-day carry, out of
 * computeClosedToday's own today-only scope) still gets an EXIT event with
 * realizedUsd:null rather than being silently dropped -- a real fill is
 * never invisible to the world. */
export function buildTradeMomentEvents(
  fills: readonly FillRow[],
  closed: readonly ClosedPosition[],
): TradeMomentEvent[] {
  const realizedByActivityId = new Map<string, number>();
  for (const c of closed) {
    realizedByActivityId.set(c.exitActivityId, (realizedByActivityId.get(c.exitActivityId) ?? 0) + c.realizedUsd);
  }
  const out: TradeMomentEvent[] = [];
  for (const f of fills) {
    if (f.side === "buy") {
      out.push({
        activityId: f.activityId,
        arm: f.arm,
        kind: "ENTER",
        symbol: f.symbol,
        qty: f.qty,
        price: f.price,
        tsEt: f.ts_et,
        realizedUsd: null,
      });
    } else {
      const realized = realizedByActivityId.get(f.activityId);
      out.push({
        activityId: f.activityId,
        arm: f.arm,
        kind: "EXIT",
        symbol: f.symbol,
        qty: f.qty,
        price: f.price,
        tsEt: f.ts_et,
        realizedUsd: realized !== undefined ? Math.round(realized * 100) / 100 : null,
      });
    }
  }
  return out;
}

/** ET wall-clock string ("2026-09-15T10:55:06.438524" or with a space
 * separator) -> a comparable millisecond number. Both the fill's own ts_et
 * and the caller's "now" must be produced by this SAME "treat the ET
 * wall-clock text as if it were UTC" convention (the adapter is responsible
 * for that consistency) -- this function never touches a real timezone
 * database, it only needs INTERNALLY consistent deltas between two ET
 * wall-clock strings, which this trick gives for free without a TZ
 * dependency in a pure module. */
export function etTsToComparableMs(tsEt: string): number {
  const iso = tsEt.includes("T") ? tsEt : tsEt.replace(" ", "T");
  const withZ = /Z$/.test(iso) ? iso : `${iso}Z`;
  const ms = Date.parse(withZ);
  return Number.isNaN(ms) ? 0 : ms;
}

const DEFAULT_WINDOW_SEC = 75; // bounded 60-90s per spec, midpoint

/** Filters to the events still inside their bubble/ticker window --
 * `nowEtComparableMs` MUST be produced by etTsToComparableMs on the SAME
 * "now" wall-clock representation the adapter computed fill timestamps
 * from. A fill in the future (clock skew) is excluded too (age < 0), never
 * shown as "still active" by a negative-age bug. Newest-first, so a caller
 * that only wants ONE (the Pilot bubble) can just take events[0]. */
export function activeTradeMoments(
  events: readonly TradeMomentEvent[],
  nowEtComparableMs: number,
  windowSec: number = DEFAULT_WINDOW_SEC,
): TradeMomentEvent[] {
  return events
    .map((ev) => ({ ev, ageMs: nowEtComparableMs - etTsToComparableMs(ev.tsEt) }))
    .filter(({ ageMs }) => ageMs >= 0 && ageMs <= windowSec * 1000)
    .sort((a, b) => a.ageMs - b.ageMs) // smallest age (most recent) first
    .map(({ ev }) => ev);
}
