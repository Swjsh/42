import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Gamma",
  description: "Gamma's live presence — what I'm doing, what I traded, what I'm working on this week.",
};

export default function GammaAppLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
