"use client";

import { useCockpit } from "@/lib/cockpit-data";
import { CockpitShell } from "@/components/cockpit/shell";
import { KpiRow } from "@/components/cockpit/kpi-row";
import { RoutingMap } from "@/components/cockpit/routing-map";
import { CostPulse } from "@/components/cockpit/cost-pulse";
import { NeedsYou, useFireCard } from "@/components/cockpit/needs-you";
import { AgentHealth } from "@/components/cockpit/agent-health";
import { SystemAlerts } from "@/components/cockpit/alerts";
import { ArmyPanel } from "@/components/cockpit/army-panel";
import { ProducerTiles } from "@/components/cockpit/producer-tiles";
import { ChatDock } from "@/components/cockpit/chat-dock";
import { Skeleton } from "@/components/ui/skeleton";

function LoadingGrid() {
  return (
    <div className="cockpit min-h-screen p-8">
      <div className="grid grid-cols-6 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-2xl" />
        ))}
      </div>
      <Skeleton className="mt-4 h-[420px] rounded-2xl" />
    </div>
  );
}

function PayloadError({ message }: { message: string }) {
  return (
    <div className="cockpit min-h-screen grid place-items-center p-8">
      <div className="gc-glass max-w-md p-8 text-center">
        <div className="gc-icon-tile mx-auto mb-4">!</div>
        <div className="text-lg font-semibold">Cockpit payload unreadable</div>
        <p className="mt-2 text-[14px] text-[var(--gc-text-2)]">
          The command center reads <span className="font-medium">payload.json</span>, written by the
          Gamma_Home task every 30 minutes. Regenerate it with the home generator and reload.
        </p>
        <p className="mt-3 text-[13px] text-[var(--gc-text-3)]">{message}</p>
      </div>
    </div>
  );
}

export default function CockpitApp({ companionOnline }: { companionOnline: boolean }) {
  const { data, error, isLoading } = useCockpit();
  const { fire } = useFireCard();

  if (isLoading && !data) return <LoadingGrid />;
  if (error && !data) return <PayloadError message={String(error.message ?? error)} />;
  if (!data) return <PayloadError message="empty payload" />;

  const topCard = data.cards?.cards?.[0];

  return (
    <CockpitShell
      data={data}
      companionOnline={companionOnline}
      onFireTop={topCard ? () => fire(topCard) : undefined}
    >
      <section id="command" className="space-y-4">
        <KpiRow data={data} />
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(340px,1fr)]">
          <RoutingMap data={data} />
          <NeedsYou data={data} limit={5} />
        </div>
        <div id="army" className="grid gap-4 xl:grid-cols-3">
          <ArmyPanel data={data} />
          <AgentHealth data={data} />
          <CostPulse data={data} />
        </div>
        <SystemAlerts data={data} />
      </section>

      <section id="research" className="mt-8">
        <ProducerTiles data={data} />
      </section>

      <ChatDock />
    </CockpitShell>
  );
}
