import { AppShell } from "@/components/app-shell";
import { LearningStudio } from "@/components/learning-studio";
import { getDashboardOverview } from "@/lib/italix-api";

export const dynamic = "force-dynamic";

export default async function LearningPage() {
  const overview = await getDashboardOverview();
  return (
    <AppShell connected={overview.ok}>
      <div className="mx-auto w-full max-w-[1480px]">
        <div className="mb-7 max-w-3xl">
          <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-violet-400">
            Specialist operations
          </p>
          <h2 className="text-balance text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
            Learning, with every gate visible.
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
            Inspect approved-example readiness, local training runs, and adapter qualification without changing system state.
          </p>
        </div>
        <LearningStudio />
      </div>
    </AppShell>
  );
}
