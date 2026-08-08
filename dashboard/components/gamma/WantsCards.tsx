import type { WantItem } from "@/lib/gamma-app-types";

export default function WantsCards({ wants }: { wants: WantItem[] }) {
  return (
    <>
      {wants.length > 0 ? (
        <ol className="flex flex-col gap-2">
          {wants.map((w) => (
            <li
              key={w.id}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5 text-sm"
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
            >
              <span
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                style={{ background: "var(--cyan-soft, rgba(34,211,238,.16))", color: "var(--cyan)" }}
              >
                {w.priority}
              </span>
              <span style={{ color: "var(--text-1)" }}>{w.text}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-3)" }}>
          —
        </p>
      )}
    </>
  );
}
