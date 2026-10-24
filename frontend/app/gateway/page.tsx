import { AppShell } from "@/components/app-shell";
import { GatewayPlayground } from "@/components/gateway-playground";
import { getDashboardOverview } from "@/lib/italix-api";

export const dynamic = "force-dynamic";

export default async function GatewayPage() {
  const result = await getDashboardOverview();
  const models = result.ok ? result.overview.active_models : [];

  return (
    <AppShell connected={result.ok}>
      <div className="mx-auto w-full max-w-[1480px]">
        <div className="mb-7 max-w-3xl">
          <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-violet-400">
            Local inference
          </p>
          <h2 className="text-balance text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
            Route work with evidence.
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
            Exercise active specialists through the private gateway. Cloud routing and trace capture remain disabled.
          </p>
        </div>
        <GatewayPlayground activeModels={models} />
      </div>
    </AppShell>
  );
}
