import { AppShell } from "@/components/app-shell";
import { OverviewDashboard } from "@/components/overview-dashboard";
import { getDashboardOverview } from "@/lib/italix-api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const result = await getDashboardOverview();
  return (
    <AppShell connected={result.ok}>
      <div className="mx-auto w-full max-w-[1480px]">
        <div className="mb-7 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-violet-400">
              Command center
            </p>
            <h2 className="text-balance text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
              Infrastructure at a glance.
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-zinc-500">
              Real gateway activity, specialist readiness, and active workload routing.
            </p>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-zinc-700">Observed data · local control plane</p>
        </div>
        <OverviewDashboard result={result} />
      </div>
    </AppShell>
  );
}
