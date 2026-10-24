import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Boxes,
  BrainCircuit,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  CloudOff,
  DatabaseZap,
  FlaskConical,
  GitBranch,
  GraduationCap,
  Layers3,
  RadioTower,
  Route,
  ServerOff,
  Sparkles,
} from "lucide-react";

import {
  type ChartDatum,
  LatencyComparisonChart,
  RequestDistributionChart,
} from "@/components/overview-charts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ActiveModelKind, DashboardOverview, OverviewResult } from "@/types/dashboard";

function number(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function latency(value: number | null) {
  return value === null ? "Not measured" : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`;
}

function dollars(value: number | null) {
  return value === null
    ? "Not measured"
    : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 }).format(value);
}

const kindLabel: Record<ActiveModelKind, string> = {
  system: "Deterministic system",
  base: "Base model",
  adapter: "LoRA adapter",
};

const kindClass: Record<ActiveModelKind, string> = {
  system: "border-violet-400/15 bg-violet-400/[0.065] text-violet-300",
  base: "border-sky-400/15 bg-sky-400/[0.06] text-sky-300",
  adapter: "border-amber-400/15 bg-amber-400/[0.06] text-amber-300",
};

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="grid h-56 place-items-center rounded-lg border border-dashed border-white/[0.07] bg-black/10 px-6 text-center">
      <div>
        <CloudOff className="mx-auto size-5 text-zinc-700" aria-hidden="true" />
        <p className="mt-3 text-xs text-zinc-500">{message}</p>
      </div>
    </div>
  );
}

function OfflineState({ message }: { message: string }) {
  return (
    <Card className="border-amber-400/[0.12] bg-[#0d0d11]/88 shadow-[0_24px_80px_rgb(0_0_0/0.26)]">
      <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 text-center">
        <div className="grid size-12 place-items-center rounded-xl border border-amber-400/15 bg-amber-400/[0.06] text-amber-300">
          <ServerOff className="size-5" aria-hidden="true" />
        </div>
        <Badge variant="outline" className="mt-5 border-amber-400/15 bg-amber-400/[0.05] text-amber-300">
          <AlertTriangle aria-hidden="true" /> Backend unavailable
        </Badge>
        <h3 className="mt-4 text-lg font-medium tracking-[-0.02em] text-zinc-100">Overview data could not be loaded</h3>
        <p className="mt-2 max-w-lg text-sm leading-6 text-zinc-500">{message}</p>
        <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-zinc-700">
          The command center will recover when the private backend reconnects
        </p>
      </CardContent>
    </Card>
  );
}

function KpiCard({
  label,
  value,
  detail,
  icon: Icon,
  accent = "violet",
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
  accent?: "violet" | "emerald" | "sky" | "amber";
}) {
  const styles = {
    violet: "border-violet-400/15 bg-violet-400/[0.06] text-violet-300",
    emerald: "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300",
    sky: "border-sky-400/15 bg-sky-400/[0.06] text-sky-300",
    amber: "border-amber-400/15 bg-amber-400/[0.06] text-amber-300",
  };

  return (
    <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/82 py-0 transition-[border-color,transform,background-color] duration-200 hover:-translate-y-0.5 hover:border-white/[0.12] hover:bg-[#101014]">
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-[11px] font-medium uppercase tracking-[0.11em] text-zinc-500">{label}</p>
          <div className={cn("grid size-8 shrink-0 place-items-center rounded-lg border", styles[accent])}>
            <Icon className="size-3.5" aria-hidden="true" />
          </div>
        </div>
        <p className="mt-4 break-words text-2xl font-semibold tracking-[-0.04em] text-zinc-50">{value}</p>
        <p className="mt-1.5 min-h-8 text-[11px] leading-4 text-zinc-600">{detail}</p>
      </CardContent>
    </Card>
  );
}

function Charts({ overview }: { overview: DashboardOverview }) {
  const requestData: ChartDatum[] = [
    { name: "Deterministic", value: overview.observed_usage.deterministic_requests, color: "#a78bfa" },
    { name: "Local model", value: overview.observed_usage.model_inference_requests, color: "#38bdf8" },
    { name: "Cloud", value: overview.observed_usage.cloud_requests, color: "#fbbf24" },
    { name: "Other", value: overview.observed_usage.other_requests, color: "#71717a" },
  ].filter((item) => item.value > 0);

  const latencyData: ChartDatum[] = [
    { name: "Deterministic", value: overview.latency.average_deterministic_latency_ms ?? -1, color: "#a78bfa" },
    { name: "Local model", value: overview.latency.average_model_inference_latency_ms ?? -1, color: "#38bdf8" },
    { name: "Cloud", value: overview.latency.average_cloud_latency_ms ?? -1, color: "#fbbf24" },
  ].filter((item) => item.value >= 0);

  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-2">
      <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/82 py-0">
        <CardHeader className="border-b border-white/[0.055] p-5">
          <CardTitle className="text-sm tracking-[-0.01em] text-zinc-200">Request distribution</CardTitle>
          <p className="text-xs text-zinc-600">Observed requests by execution path</p>
        </CardHeader>
        <CardContent className="p-5">
          {requestData.length ? <RequestDistributionChart data={requestData} /> : <EmptyChart message="No request activity has been observed yet." />}
        </CardContent>
      </Card>

      <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/82 py-0">
        <CardHeader className="border-b border-white/[0.055] p-5">
          <CardTitle className="text-sm tracking-[-0.01em] text-zinc-200">Latency comparison</CardTitle>
          <p className="text-xs text-zinc-600">Observed average latency; absent paths are omitted</p>
        </CardHeader>
        <CardContent className="p-5">
          {latencyData.length ? <LatencyComparisonChart data={latencyData} /> : <EmptyChart message="No latency measurements are available yet." />}
        </CardContent>
      </Card>
    </div>
  );
}

function ActiveRoutes({ overview }: { overview: DashboardOverview }) {
  return (
    <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/82 py-0">
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] items-center border-b border-white/[0.055] p-5">
        <div>
          <CardTitle className="text-sm tracking-[-0.01em] text-zinc-200">Active routes</CardTitle>
          <p className="mt-1 text-xs text-zinc-600">Current workload routing from the model registry</p>
        </div>
        <Badge variant="outline" className="border-white/[0.08] bg-white/[0.025] text-zinc-400">
          <Route aria-hidden="true" /> {overview.active_models.length} active
        </Badge>
      </CardHeader>
      <CardContent className="p-0">
        {overview.active_models.length ? (
          <div className="divide-y divide-white/[0.055]">
            {overview.active_models.map((model) => (
              <div key={`${model.workload}-${model.id}`} className="grid gap-3 px-5 py-4 transition-colors hover:bg-white/[0.018] sm:grid-cols-[minmax(8rem,0.8fr)_minmax(14rem,1.7fr)_minmax(10rem,1fr)_auto] sm:items-center">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.12em] text-zinc-700 sm:hidden">Workload</p>
                  <p className="mt-1 font-mono text-xs text-zinc-300 sm:mt-0">{model.workload}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-[0.12em] text-zinc-700 sm:hidden">Model</p>
                  <p className="mt-1 break-all font-mono text-xs leading-5 text-zinc-100 sm:mt-0" title={model.id}>{model.id}</p>
                </div>
                <div>
                  <Badge variant="outline" className={kindClass[model.kind]}>{kindLabel[model.kind]}</Badge>
                </div>
                <div className="flex items-center gap-2 text-xs text-emerald-300">
                  <span className="size-1.5 rounded-full bg-emerald-400" />
                  {model.status}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid min-h-36 place-items-center px-6 text-center text-xs text-zinc-600">No active routes are registered.</div>
        )}
      </CardContent>
    </Card>
  );
}

function Lifecycle({ overview }: { overview: DashboardOverview }) {
  const evaluation = overview.latest_evaluation;
  const stages = [
    { label: "Observe", icon: RadioTower, value: `${number(overview.total_requests)} requests`, detail: "Gateway activity" },
    { label: "Teach", icon: GraduationCap, value: `${number(overview.queue_pending)} pending`, detail: "Approved examples" },
    { label: "Train", icon: BrainCircuit, value: `${number(overview.training_jobs_completed)} completed`, detail: "Training jobs" },
    { label: "Evaluate", icon: FlaskConical, value: evaluation ? `${evaluation.passed}/${evaluation.total} passed` : "No result", detail: evaluation ? (evaluation.qualified ? "Latest qualified" : "Latest not qualified") : "No evaluation recorded" },
    { label: "Deploy", icon: GitBranch, value: `${number(overview.active_models.length)} active`, detail: "Workload routes" },
  ];

  return (
    <Card className="min-w-0 gap-0 border-white/[0.07] bg-[linear-gradient(135deg,rgba(124,58,237,0.055),rgba(13,13,17,0.82)_38%)] py-0">
      <CardHeader className="border-b border-white/[0.055] p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-violet-400" aria-hidden="true" />
          <CardTitle className="text-sm tracking-[-0.01em] text-zinc-200">Specialist lifecycle</CardTitle>
        </div>
        <p className="text-xs text-zinc-600">An evidence trail from observation to controlled deployment</p>
      </CardHeader>
      <CardContent className="grid gap-2 p-4 sm:grid-cols-5">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          return (
            <div key={stage.label} className="relative min-w-0 rounded-lg border border-white/[0.055] bg-black/15 p-4 transition-colors hover:border-violet-400/[0.13] hover:bg-violet-400/[0.025]">
              <div className="flex items-center justify-between">
                <div className="grid size-8 place-items-center rounded-lg border border-violet-400/[0.12] bg-violet-400/[0.055] text-violet-300">
                  <Icon className="size-3.5" aria-hidden="true" />
                </div>
                {index < stages.length - 1 && <ArrowRight className="hidden size-3.5 text-zinc-800 sm:block" aria-hidden="true" />}
              </div>
              <p className="mt-4 text-xs font-medium text-zinc-300">{stage.label}</p>
              <p className="mt-2 break-words font-mono text-[11px] text-zinc-100">{stage.value}</p>
              <p className="mt-1 text-[10px] leading-4 text-zinc-600">{stage.detail}</p>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export function OverviewDashboard({ result }: { result: OverviewResult }) {
  if (!result.ok) return <OfflineState message={result.message} />;

  const { overview } = result;
  const qualified = overview.registry.qualified_lora_adapters;
  const experimental = overview.registry.experimental_lora_adapters;

  return (
    <div className="min-w-0 max-w-full space-y-4 overflow-hidden">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <KpiCard label="Total requests" value={number(overview.total_requests)} detail={`${number(overview.successful_requests)} successful · ${number(overview.failed_requests)} failed`} icon={Activity} accent="violet" />
        <KpiCard label="Execution split" value={`${number(overview.deterministic_requests)} / ${number(overview.model_inference_requests)}`} detail="Deterministic / local model" icon={Layers3} accent="sky" />
        <KpiCard label="Average latency" value={latency(overview.average_local_latency_ms)} detail="All observed local execution" icon={Clock3} accent="emerald" />
        <KpiCard label="Training jobs" value={number(overview.training_jobs_completed)} detail="Completed jobs; no action implied" icon={DatabaseZap} accent="violet" />
        <KpiCard label="LoRA adapters" value={`${number(experimental)} / ${number(qualified)}`} detail={`Experimental / qualified${qualified === 0 ? " · zero qualified" : ""}`} icon={BadgeCheck} accent="amber" />
        <KpiCard label="Cloud spending" value={dollars(overview.measured_cloud_cost_usd)} detail={overview.costs.note || "Measured cloud usage only"} icon={CircleDollarSign} accent="emerald" />
      </div>

      <Charts overview={overview} />
      <ActiveRoutes overview={overview} />
      <Lifecycle overview={overview} />

      <div className="flex flex-col gap-2 rounded-lg border border-white/[0.055] bg-white/[0.015] px-4 py-3 text-[10px] text-zinc-700 sm:flex-row sm:items-center sm:justify-between">
        <span className="flex items-center gap-2"><CheckCircle2 className="size-3 text-emerald-500" aria-hidden="true" /> Authenticated viewer data · server-rendered</span>
        <span className="flex items-center gap-2"><Boxes className="size-3 text-violet-500" aria-hidden="true" /> Deterministic systems are reported separately from trained adapters</span>
      </div>
    </div>
  );
}
