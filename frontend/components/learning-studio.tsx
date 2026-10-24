"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  BadgeCheck,
  Ban,
  BookOpenCheck,
  Boxes,
  BrainCircuit,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Cpu,
  Database,
  FlaskConical,
  Gauge,
  GitBranch,
  Layers3,
  MemoryStick,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TimerReset,
} from "lucide-react";

import { OperatorUnlock } from "@/components/gateway-playground";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { LearningJob, LearningModel, LearningStudioData } from "@/types/learning";

type StudioState = "checking" | "locked" | "loading" | "ready" | "error";

function integer(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function decimal(value: number | null, suffix = "") {
  return value === null ? "Not recorded" : `${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}${suffix}`;
}

function date(value: string | null) {
  if (!value) return "Not completed";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "Unknown date" : new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

const statusTone: Record<string, string> = {
  completed: "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300",
  qualified: "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300",
  planned: "border-sky-400/15 bg-sky-400/[0.06] text-sky-300",
  running: "border-violet-400/15 bg-violet-400/[0.06] text-violet-300",
  experimental_failed: "border-rose-400/15 bg-rose-400/[0.055] text-rose-300",
  failed: "border-rose-400/15 bg-rose-400/[0.055] text-rose-300",
};

function StatusBadge({ status }: { status: string }) {
  return <Badge variant="outline" className={statusTone[status] ?? "border-white/[0.08] bg-white/[0.025] text-zinc-400"}>{status.replaceAll("_", " ")}</Badge>;
}

function LoadingStudio() {
  return (
    <div className="space-y-4" aria-label="Loading Learning Studio">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-xl" />)}</div>
      <div className="grid gap-4 xl:grid-cols-2"><Skeleton className="h-72 rounded-xl" /><Skeleton className="h-72 rounded-xl" /></div>
      <Skeleton className="h-80 rounded-xl" />
    </div>
  );
}

function SummaryCards({ data }: { data: LearningStudioData }) {
  const cards = [
    { label: "Approved examples", value: integer(data.summary.pending_examples), detail: "Pending across workloads", icon: BookOpenCheck, tone: "violet" },
    { label: "Training readiness", value: `${data.summary.ready_workloads} / ${data.queues.length}`, detail: "Workloads meeting minimum", icon: Gauge, tone: "sky" },
    { label: "Training jobs", value: integer(data.summary.completed_jobs), detail: `${data.summary.planned_jobs} planned · ${data.summary.failed_jobs} failed`, icon: BrainCircuit, tone: "emerald" },
    { label: "LoRA qualification", value: `${data.summary.experimental_adapters} / ${data.summary.qualified_adapters}`, detail: "Experimental / qualified", icon: BadgeCheck, tone: "amber" },
  ] as const;
  const tones = {
    violet: "border-violet-400/15 bg-violet-400/[0.06] text-violet-300",
    sky: "border-sky-400/15 bg-sky-400/[0.06] text-sky-300",
    emerald: "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300",
    amber: "border-amber-400/15 bg-amber-400/[0.06] text-amber-300",
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon;
        return <Card key={card.label} className="gap-0 border-white/[0.07] bg-[#0d0d11]/84 py-0 transition-[transform,border-color] hover:-translate-y-0.5 hover:border-white/[0.12]"><CardContent className="p-5"><div className="flex items-start justify-between"><p className="text-[10px] font-medium uppercase tracking-[0.12em] text-zinc-600">{card.label}</p><span className={cn("grid size-8 place-items-center rounded-lg border", tones[card.tone])}><Icon className="size-3.5" /></span></div><p className="mt-4 text-2xl font-semibold tracking-[-0.04em] text-zinc-50">{card.value}</p><p className="mt-1.5 text-[11px] text-zinc-600">{card.detail}</p></CardContent></Card>;
      })}
    </div>
  );
}

function Readiness({ data }: { data: LearningStudioData }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {data.queues.map((queue) => {
        const progress = queue.minimum_examples > 0 ? Math.min(100, (queue.pending / queue.minimum_examples) * 100) : 0;
        const config = data.configurations.find((item) => item.workload === queue.workload);
        return (
          <Card key={queue.workload} className="gap-0 border-white/[0.07] bg-[#0d0d11]/84 py-0">
            <CardHeader className="border-b border-white/[0.055] p-5">
              <div className="flex items-start justify-between gap-4"><div><p className="font-mono text-xs text-zinc-200">{queue.workload}</p><p className="mt-1 text-xs text-zinc-600">Approved-example readiness</p></div>{queue.enough_examples ? <Badge variant="outline" className={statusTone.qualified}><CheckCircle2 /> Ready</Badge> : <Badge variant="outline" className="border-amber-400/15 bg-amber-400/[0.055] text-amber-300"><Clock3 /> Collecting</Badge>}</div>
            </CardHeader>
            <CardContent className="p-5">
              <div className="flex items-end justify-between gap-4"><div><p className="text-3xl font-semibold tracking-[-0.045em] text-white">{queue.pending}<span className="ml-1.5 text-base font-normal text-zinc-600">/ {queue.minimum_examples}</span></p><p className="mt-1 text-[11px] text-zinc-600">pending approved examples</p></div><p className="font-mono text-[10px] text-zinc-700">{Math.round(progress)}%</p></div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.055]"><div className={cn("h-full rounded-full", queue.enough_examples ? "bg-emerald-400" : "bg-violet-400")} style={{ width: `${progress}%` }} /></div>
              <div className="mt-5 grid grid-cols-3 gap-2 text-center">{["used", "excluded", "pending"].map((key) => <div key={key} className="rounded-lg border border-white/[0.055] bg-black/15 px-2 py-2.5"><p className="font-mono text-xs text-zinc-300">{queue.counts[key] ?? 0}</p><p className="mt-1 text-[9px] uppercase tracking-wider text-zinc-700">{key}</p></div>)}</div>
              {config && <div className="mt-5 flex items-center gap-2 border-t border-white/[0.055] pt-4 text-[10px] text-zinc-600"><Cpu className="size-3 text-violet-400" /><span className="truncate">{config.engine} · rank-{config.rank} · {config.optimizer_steps} steps</span><span className="ml-auto shrink-0">local only</span></div>}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function Workflow({ data }: { data: LearningStudioData }) {
  const latestJob = data.jobs[0];
  const stages = [
    { label: "Teach", icon: BookOpenCheck, value: `${data.summary.pending_examples} pending`, detail: "Approved feedback only" },
    { label: "Train", icon: BrainCircuit, value: latestJob ? latestJob.status : "No jobs", detail: latestJob?.candidate_id ?? "No recent candidate" },
    { label: "Evaluate", icon: FlaskConical, value: `${data.summary.experimental_adapters} experimental`, detail: `${data.summary.qualified_adapters} qualified adapters` },
    { label: "Deploy", icon: GitBranch, value: `${data.models.filter((model) => model.active).length} active routes`, detail: "Separate controlled gate" },
  ];
  return (
    <Card className="gap-0 border-white/[0.07] bg-[linear-gradient(135deg,rgba(124,58,237,0.055),rgba(13,13,17,0.84)_38%)] py-0">
      <CardHeader className="border-b border-white/[0.055] p-5"><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><Sparkles className="size-4 text-violet-400" /> Controlled learning workflow</CardTitle><p className="text-xs text-zinc-600">Every transition remains explicit and independently gated</p></CardHeader>
      <CardContent className="grid gap-2 p-4 sm:grid-cols-4">{stages.map((stage, index) => { const Icon = stage.icon; return <div key={stage.label} className="rounded-lg border border-white/[0.055] bg-black/15 p-4"><div className="flex items-center justify-between"><span className="grid size-8 place-items-center rounded-lg border border-violet-400/15 bg-violet-400/[0.06] text-violet-300"><Icon className="size-3.5" /></span>{index < stages.length - 1 && <ArrowRight className="hidden size-3.5 text-zinc-800 sm:block" />}</div><p className="mt-4 text-xs font-medium text-zinc-300">{stage.label}</p><p className="mt-2 truncate font-mono text-[11px] text-zinc-100">{stage.value}</p><p className="mt-1 truncate text-[10px] text-zinc-600">{stage.detail}</p></div>; })}</CardContent>
    </Card>
  );
}

function JobMetrics({ job }: { job: LearningJob }) {
  const metrics = [
    ["Duration", decimal(job.metrics.duration_seconds, "s")],
    ["Peak memory", decimal(job.metrics.peak_mlx_memory_gb, " GB")],
    ["Train loss", decimal(job.metrics.final_training_loss)],
    ["Valid loss", decimal(job.metrics.final_validation_loss)],
  ];
  return <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-lg border border-white/[0.05] bg-black/15 px-3 py-2.5"><p className="text-[9px] uppercase tracking-wider text-zinc-700">{label}</p><p className="mt-1 font-mono text-[11px] text-zinc-300">{value}</p></div>)}</div>;
}

function TrainingJobs({ jobs }: { jobs: LearningJob[] }) {
  return (
    <Card className="gap-0 border-white/[0.07] bg-[#0d0d11]/84 py-0">
      <CardHeader className="border-b border-white/[0.055] p-5"><div className="flex items-center justify-between"><div><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><TimerReset className="size-4 text-violet-400" /> Training jobs</CardTitle><p className="mt-1 text-xs text-zinc-600">Recorded local runs and sanitized result metrics</p></div><Badge variant="outline" className="border-white/[0.08] text-zinc-500">{jobs.length} jobs</Badge></div></CardHeader>
      <CardContent className="p-0">{jobs.length ? <div className="divide-y divide-white/[0.055]">{jobs.map((job, index) => <div key={job.id} className="relative px-5 py-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div className="flex min-w-0 gap-3"><div className="relative mt-0.5"><span className={cn("grid size-8 place-items-center rounded-full border", job.status === "completed" ? "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300" : "border-white/[0.08] bg-white/[0.025] text-zinc-500")}>{job.status === "completed" ? <CheckCircle2 className="size-3.5" /> : <CircleDashed className="size-3.5" />}</span>{index < jobs.length - 1 && <span className="absolute left-1/2 top-8 hidden h-8 w-px -translate-x-1/2 bg-white/[0.06] sm:block" />}</div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="break-all font-mono text-xs text-zinc-200">{job.candidate_id ?? `job-${job.id}`}</p><StatusBadge status={job.status} /></div><p className="mt-1.5 text-[11px] text-zinc-600">{job.workload} · {job.example_count} examples · {date(job.completed_at ?? job.created_at)}</p></div></div>{job.metrics.evaluation_passed !== null && <p className="font-mono text-[11px] text-zinc-400">Evaluation {job.metrics.evaluation_passed}/{job.metrics.evaluation_total ?? "?"}</p>}</div><JobMetrics job={job} /></div>)}</div> : <div className="grid min-h-48 place-items-center text-center"><div><Database className="mx-auto size-5 text-zinc-700" /><p className="mt-3 text-xs text-zinc-600">No training jobs have been recorded.</p></div></div>}</CardContent>
    </Card>
  );
}

function AdapterCard({ adapter }: { adapter: LearningModel }) {
  const reason = adapter.qualification_reason ?? (adapter.status === "experimental_failed" ? "No detailed qualification reason is recorded; the registry marks this candidate as failed." : "No qualification result recorded.");
  return <div className="rounded-xl border border-white/[0.06] bg-black/15 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="break-all font-mono text-xs text-zinc-200">{adapter.id}</p><p className="mt-1 text-[10px] text-zinc-600">{adapter.workload} · {date(adapter.created_at)}</p></div><StatusBadge status={adapter.status} /></div>{adapter.evaluation_passed !== null && <div className="mt-4 flex items-center gap-2 text-[11px] text-zinc-500"><FlaskConical className="size-3 text-violet-400" /> Evaluation <span className="font-mono text-zinc-300">{adapter.evaluation_passed}/{adapter.evaluation_total ?? "?"}</span></div>}<p className="mt-3 border-t border-white/[0.055] pt-3 text-[11px] leading-5 text-zinc-600">{reason}</p></div>;
}

function Registry({ data }: { data: LearningStudioData }) {
  const adapters = data.models.filter((model) => model.kind === "adapter");
  return (
    <Card className="gap-0 border-white/[0.07] bg-[#0d0d11]/84 py-0">
      <CardHeader className="border-b border-white/[0.055] p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><Boxes className="size-4 text-violet-400" /> Adapter registry</CardTitle><p className="mt-1 text-xs text-zinc-600">Experimental candidates and their recorded qualification outcome</p></div><div className="flex gap-2"><Badge variant="outline" className="border-amber-400/15 text-amber-300">{data.summary.experimental_adapters} experimental</Badge><Badge variant="outline" className="border-emerald-400/15 text-emerald-300">{data.summary.qualified_adapters} qualified</Badge></div></div></CardHeader>
      <CardContent className="p-5">{data.summary.qualified_adapters === 0 && <div className="mb-4 flex items-start gap-3 rounded-xl border border-rose-400/[0.11] bg-rose-400/[0.035] p-4"><ShieldAlert className="mt-0.5 size-4 shrink-0 text-rose-300" /><div><p className="text-xs font-medium text-rose-200">No LoRA adapter is production-qualified</p><p className="mt-1 text-[11px] leading-5 text-zinc-600">Every registered adapter remains blocked by its evaluation status. Active deterministic systems and base models are separate from LoRA qualification.</p></div></div>} {adapters.length ? <div className="grid gap-3 lg:grid-cols-2">{adapters.map((adapter) => <AdapterCard key={adapter.id} adapter={adapter} />)}</div> : <div className="grid min-h-36 place-items-center text-xs text-zinc-600">No adapters are registered.</div>}</CardContent>
    </Card>
  );
}

function Configurations({ data }: { data: LearningStudioData }) {
  return <Card className="gap-0 border-white/[0.07] bg-[#0d0d11]/84 py-0"><CardHeader className="border-b border-white/[0.055] p-5"><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><Layers3 className="size-4 text-violet-400" /> Training configuration</CardTitle><p className="text-xs text-zinc-600">Read-only public configuration from the local MLX-LM runner</p></CardHeader><CardContent className="grid gap-3 p-5 lg:grid-cols-2">{data.configurations.map((config) => <div key={config.workload} className="rounded-xl border border-white/[0.06] bg-black/15 p-4"><div className="flex items-center justify-between gap-3"><p className="font-mono text-xs text-zinc-200">{config.workload}</p><Badge variant="outline" className="border-violet-400/15 text-violet-300">rank {config.rank}</Badge></div><p className="mt-3 break-all font-mono text-[10px] leading-5 text-zinc-500">{config.base_model}</p><div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-white/[0.055] pt-4 text-[10px]"><p className="text-zinc-600">Trainable layers <span className="float-right font-mono text-zinc-300">{config.trainable_layers}</span></p><p className="text-zinc-600">Optimizer steps <span className="float-right font-mono text-zinc-300">{config.optimizer_steps}</span></p><p className="text-zinc-600">Peak estimate <span className="float-right font-mono text-zinc-300">{config.estimated_resources.peak_mlx_memory_gb} GB</span></p><p className="text-zinc-600">Duration estimate <span className="float-right font-mono text-zinc-300">{config.estimated_resources.duration_seconds}s</span></p></div></div>)}</CardContent></Card>;
}

export function LearningStudio() {
  const [state, setState] = useState<StudioState>("checking");
  const [data, setData] = useState<LearningStudioData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const response = await fetch("/api/operator/learning", { cache: "no-store" });
      const body: unknown = await response.json().catch(() => null);
      if (response.status === 401) { setState("locked"); return; }
      if (!response.ok) {
        const detail = body && typeof body === "object" && "detail" in body ? String((body as { detail: unknown }).detail) : "Learning status is unavailable.";
        setError(detail); setState("error"); return;
      }
      setData(body as LearningStudioData); setState("ready");
    } catch { setError("The local learning-status endpoint is unavailable."); setState("error"); }
  }, []);

  useEffect(() => {
    fetch("/api/operator/session", { cache: "no-store" })
      .then(async (response) => { const body = await response.json().catch(() => null) as { authenticated?: boolean } | null; if (response.ok && body?.authenticated) await load(); else setState("locked"); })
      .catch(() => setState("locked"));
  }, [load]);

  if (state === "checking" || state === "loading") return <LoadingStudio />;
  if (state === "locked") return <OperatorUnlock onUnlocked={() => void load()} />;
  if (state === "error" || !data) return <Card className="border-rose-400/[0.12] bg-[#0d0d11]/84"><CardContent className="grid min-h-64 place-items-center p-6 text-center"><div><AlertCircle className="mx-auto size-6 text-rose-300" /><h3 className="mt-4 text-sm font-medium text-zinc-200">Learning status unavailable</h3><p className="mt-2 max-w-md text-xs leading-5 text-zinc-600">{error}</p><button type="button" onClick={() => void load()} className="mx-auto mt-4 flex h-9 items-center gap-2 rounded-lg border border-white/[0.08] px-3 text-xs text-zinc-400 hover:bg-white/[0.04]"><RefreshCw className="size-3.5" /> Retry</button></div></CardContent></Card>;

  return <div className="space-y-4"><div className="flex items-center justify-between rounded-lg border border-white/[0.055] bg-white/[0.015] px-4 py-3"><p className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-zinc-600"><Ban className="size-3 text-violet-400" /> Read-only studio · no training or deployment actions</p><p className="hidden items-center gap-2 font-mono text-[10px] text-zinc-700 sm:flex"><MemoryStick className="size-3" /> Aggregates only · examples excluded</p></div><SummaryCards data={data} /><Readiness data={data} /><Workflow data={data} /><TrainingJobs jobs={data.jobs} /><Registry data={data} /><Configurations data={data} /></div>;
}
