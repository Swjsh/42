import type { Metadata } from "next";
import { fetchCompanionToken } from "@/lib/companion-token";
import CockpitApp from "./cockpit-app";

export const metadata: Metadata = { title: "Gamma Command Center" };
export const dynamic = "force-dynamic";

export default async function CockpitPage() {
  const token = await fetchCompanionToken();
  return (
    <>
      {/* Read by the client components exactly the way the companion's own page does. */}
      <meta name="gamma-token" content={token ?? ""} />
      <CockpitApp companionOnline={Boolean(token)} />
    </>
  );
}
