"use client";

import useSWR from "swr";
import Section from "./Section";
import type { PresenceView, FleetArmPnl, GammaAppView } from "@/lib/gamma-app-types";

const PLACEHOLDER = "—";

async function fleetFetcher(url: string): Promise<GammaAppView> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as GammaAppView;
}

function fmtSigned(n: number): string {
  return `${n >= 0 ? "+" : "-"}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** One arm's progress bar toward J's per-account $100-200/day target
 * (CLAUDE.md 2026-08-07: the target is PER ACCOUNT, not book-wide). The bar
 * fill scales 0-100% across $0-targetHigh, with a tick mark at targetLow so
 * the $100-200 band itself is visible on the track. A LOSING day is a
 * structurally different visual (red fill growing on a red-tinted track)
 * from a merely-not-there-yet day (cyan fill on a neutral track) -- per J's
 * explicit requirement, a 0%-filled "not yet" bar must never read the same
 * as a real loss. */
function ArmProgressBar({ arm }: { arm: FleetArmPnl }) {
  const { displayName, todayPnl, todayTrades, targetLow, targetHigh, weekPnl, allTimePnl } = arm;
  const isLoss = todayPnl < 0;
  const isWin = todayPnl > 0;
  const hitTarget = todayPnl >= targetLow;
  const scale = targetHigh > 0 ? targetHigh : 1;
  const fillPct = Math.max(0, Math.min(100, (Math.abs(todayPnl) / scale) * 100));
  const lowTickPct = Math.max(0, Math.min(100, (targetLow / scale) * 100));
  const fillColor = isLoss ? "var(--down)" : hitTarget ? "var(--up)" : "var(--cyan)";
  const trackBg = isLoss ? "var(--down-soft)" : "var(--border)";
  const pnlColor = isLoss ? "var(--down)" : isWin ? "var(--up)" : "var(--text-2)";

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span style={{ color: "var(--text-1)" }}>{displayName}</span>
        <span className="font-mono text-sm font-semibold" style={{ color: pnlColor }}>
          {fmtSigned(todayPnl)}
        </span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full" style={{ background: trackBg }}>
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${fillPct}%`, background: fillColor }}
        />
        {/* target-band tick marks at $targetLow and $targetHigh */}
        <div
          className="absolute inset-y-0 w-px"
          style={{ left: `${lowTickPct}%`, background: "var(--border-strong)" }}
        />
        <div className="absolute inset-y-0 right-0 w-px" style={{ background: "var(--border-strong)" }} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-1 text-[11px]" style={{ color: "var(--text-4)" }}>
        <span>
          {todayTrades} trade{todayTrades !== 1 ? "s" : ""} today · target ${targetLow}-{targetHigh}
        </span>
        <span>
          wk {fmtSigned(weekPnl)} · all-time {fmtSigned(allTimePnl)}
        </span>
      </div>
    </div>
  );
}

/** Secondary book-wide rollup -- deliberately smaller/less prominent than
 * the per-arm bars above it (per-arm real numbers are the primary signal;
 * this is the aggregate context line). */
function BookWideRollup({ arms }: { arms: FleetArmPnl[] }) {
  const total = arms.reduce((sum, a) => sum + a.todayPnl, 0);
  const tone = total > 0 ? "var(--up)" : total < 0 ? "var(--down)" : "var(--text-2)";
  return (
    <p className="pt-1 text-xs" style={{ color: "var(--text-4)" }}>
      Book-wide:{" "}
      <span style={{ color: tone, fontWeight: 500 }}>
        {fmtSigned(total)}
      </span>{" "}
      of ~$500-1,000/day ({arms.length} arms) — secondary, per-arm bars above are the real target
    </p>
  );
}

function ClockRow({
  label,
  have,
  need,
  extra,
  explain,
}: {
  label: string;
  have: number | null;
  need: number;
  extra: string;
  explain?: string;
}) {
  const needSafe = need > 0 ? need : 1;
  const haveSafe = have && have > 0 ? have : 0;
  const pct = Math.max(0, Math.min(100, (Math.min(haveSafe, needSafe) / needSafe) * 100));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3 text-sm">
        <span className="w-24 shrink-0 sm:w-28" style={{ color: "var(--text-2)" }}>
          {label}
        </span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
          <div
            className="h-full rounded-full transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%`, background: "var(--cyan)" }}
          />
        </div>
        <span className="w-16 shrink-0 text-right font-mono text-xs" style={{ color: "var(--text-2)" }}>
          {have ?? PLACEHOLDER}/{need}
        </span>
        {extra && (
          <span
            className="hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline"
            style={{ background: "var(--amber-soft, rgba(245,158,11,.14))", color: "var(--amber)" }}
          >
            {extra}
          </span>
        )}
      </div>
      {explain && (
        <p className="pl-0 text-xs leading-relaxed sm:pl-[7.5rem]" style={{ color: "var(--text-4)" }}>
          {explain}
        </p>
      )}
    </div>
  );
}

export default function MoneyView({ presence }: { presence: PresenceView | null }) {
  // MoneyView needs GammaAppView.fleetPnl, which the page component (owned
  // by a sibling agent, not touched here) only forwards `presence` from --
  // so this polls the SAME "/api/gamma" key the page already polls. SWR
  // dedupes identical keys across components (shared cache, coordinated
  // revalidation), so this does not add a second real network fetch.
  const { data } = useSWR<GammaAppView>("/api/gamma", fleetFetcher, {
    refreshInterval: 20_000,
    keepPreviousData: true,
  });
  const fleetPnl = data?.fleetPnl ?? [];

  return (
    <div className="flex flex-col gap-8">
      <Section title="Goal">
        <p className="text-base" style={{ color: "var(--text-1)" }}>
          {presence?.goal_line ?? PLACEHOLDER}
        </p>
      </Section>

      <Section title="Per-arm progress (real fills, today)">
        {fleetPnl.length > 0 ? (
          <div className="flex flex-col gap-4">
            {fleetPnl.map((arm) => (
              <ArmProgressBar key={arm.armId} arm={arm} />
            ))}
            <BookWideRollup arms={fleetPnl} />
          </div>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-3)" }}>
            {PLACEHOLDER}
          </p>
        )}
      </Section>

      <Section title="My clocks">
        <div className="flex flex-col gap-3">
          {(
            presence?.clocks ?? [
              { label: "SSR shadow", have: null, need: 20, extra: "", explain: undefined },
              { label: "MES mirror", have: null, need: 20, extra: "", explain: undefined },
              { label: "Cap re-check", have: null, need: 20, extra: "", explain: undefined },
            ]
          ).map((c) => (
            <ClockRow key={c.label} {...c} />
          ))}
        </div>
      </Section>
    </div>
  );
}
