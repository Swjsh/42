import type { PresenceView, StateWord } from "@/lib/gamma-app-types";
import QuoteTicker from "./QuoteTicker";

const CHIP_COLOR: Record<StateWord, string> = {
  TRADING: "var(--up)",
  RESEARCHING: "var(--cyan)",
  "STANDING BY": "var(--text-3)",
};

function StateChip({ stateWord }: { stateWord: StateWord }) {
  const color = CHIP_COLOR[stateWord];
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold tracking-wide"
      style={{ borderColor: "var(--border-mid)", color }}
    >
      <span className="live-dot" style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
      {stateWord}
    </span>
  );
}

interface PresenceHeaderProps {
  presence: PresenceView | null;
}

const PLACEHOLDER = "—";

/** THE PRESENCE HEADER -- Gamma's identity, live state, and a first-person
 * status sentence derived from the freshest real signal (gamma_hq.py's
 * gather_state semantics, shelled out to via /api/gamma). This is the "I'm
 * here, this is what I'm doing right now" beat -- everything below it
 * (activity stream, money view, wants, this week) is supporting detail. */
export default function PresenceHeader({ presence }: PresenceHeaderProps) {
  const stateWord = presence?.state_word ?? "STANDING BY";
  return (
    <header className="flex flex-col gap-6 border-b pb-8" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <span className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text-1)" }}>
            Gamma
          </span>
          <span className="text-sm" style={{ color: "var(--text-4)" }}>
            {presence?.now_et_label ?? PLACEHOLDER}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <QuoteTicker />
          <StateChip stateWord={stateWord} />
        </div>
      </div>

      <p className="text-lg leading-relaxed" style={{ color: "var(--text-1)" }}>
        {presence?.right_now ?? "Getting my bearings — first read coming up."}
      </p>

      <p className="text-sm" style={{ color: "var(--text-3)" }}>
        Today&rsquo;s focus: {presence?.todays_focus ?? PLACEHOLDER}
      </p>
    </header>
  );
}
