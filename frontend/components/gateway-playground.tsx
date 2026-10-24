"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Binary,
  CheckCircle2,
  ChevronDown,
  CircleStop,
  Clock3,
  Code2,
  Copy,
  FileDiff,
  Fingerprint,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Play,
  Route,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UnlockKeyhole,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ActiveModel } from "@/types/dashboard";

type Workload = "pr_summary" | "change_triage";
type SessionState = "checking" | "locked" | "unlocked";

interface CompletionResponse {
  model?: string;
  choices?: Array<{ message?: { content?: string } }>;
  italix?: {
    trace_id?: string;
    workload?: string;
    route?: string;
    registry_model?: string;
    routing_reason?: string;
    validation?: Record<string, unknown> | null;
    deterministic_validation?: Record<string, unknown> | null;
    abstained?: boolean;
    abstention_reasons?: string[];
  };
}

interface InferenceResult {
  content: string;
  model: string;
  registryModel: string;
  route: string;
  traceId: string;
  latencyMs: string;
  validation: Record<string, unknown> | null;
  abstained: boolean;
  abstentionReasons: string[];
}

const SAMPLE_DIFF = `diff --git a/config.py b/config.py
index a98ce2b..ac42b1e 100644
--- a/config.py
+++ b/config.py
@@ -1,3 +1,3 @@
-REQUEST_TIMEOUT_SECONDS = 30
+REQUEST_TIMEOUT_SECONDS = 10

 def load_config():
     return {"timeout": REQUEST_TIMEOUT_SECONDS}`;

function parseResponse(value: unknown, latencyMs: string | null): InferenceResult | null {
  if (!value || typeof value !== "object") return null;
  const response = value as CompletionResponse;
  const content = response.choices?.[0]?.message?.content;
  const metadata = response.italix;
  if (typeof content !== "string" || !metadata) return null;
  return {
    content,
    model: response.model ?? "Unknown",
    registryModel: metadata.registry_model ?? "Unknown",
    route: metadata.route ?? "Unknown",
    traceId: metadata.trace_id ?? "Unavailable",
    latencyMs: latencyMs ?? "Unavailable",
    validation: metadata.deterministic_validation ?? metadata.validation ?? null,
    abstained: metadata.abstained === true,
    abstentionReasons: Array.isArray(metadata.abstention_reasons) ? metadata.abstention_reasons : [],
  };
}

function SelectField({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-2 block text-[10px] font-medium uppercase tracking-[0.13em] text-zinc-600">{label}</span>
      <span className="relative block">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-full appearance-none rounded-lg border border-white/[0.08] bg-[#0a0a0d] px-3 pr-9 font-mono text-xs text-zinc-200 outline-none transition-colors hover:border-white/[0.13] focus:border-violet-400/40 focus:ring-2 focus:ring-violet-400/10"
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 text-zinc-600" aria-hidden="true" />
      </span>
    </label>
  );
}

export function OperatorUnlock({ onUnlocked }: { onUnlocked: () => void }) {
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!secret) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret }),
      });
      setSecret("");
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        setError(body?.detail ?? "Operator unlock failed.");
        return;
      }
      onUnlocked();
    } catch {
      setError("The local session service is unavailable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-violet-400/[0.13] bg-[linear-gradient(135deg,rgba(124,58,237,0.08),rgba(13,13,17,0.92)_42%)] shadow-[0_24px_80px_rgb(0_0_0/0.3)]">
      <CardContent className="grid min-h-[25rem] place-items-center p-6">
        <form onSubmit={submit} className="w-full max-w-md text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-xl border border-violet-400/20 bg-violet-400/[0.08] text-violet-300 shadow-[0_0_36px_rgb(124_58_237/0.08)]">
            <LockKeyhole className="size-5" aria-hidden="true" />
          </div>
          <Badge variant="outline" className="mt-5 border-violet-400/15 bg-violet-400/[0.05] text-violet-300">
            Operator access
          </Badge>
          <h3 className="mt-4 text-xl font-medium tracking-[-0.025em] text-zinc-100">Unlock the local gateway</h3>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-zinc-500">
            Your unlock secret is exchanged for a short-lived, secure HttpOnly session. It is never stored in browser JavaScript.
          </p>
          <label className="mt-6 block text-left">
            <span className="sr-only">Operator unlock secret</span>
            <input
              type="password"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              autoComplete="current-password"
              required
              minLength={32}
              placeholder="Operator unlock secret"
              className="h-11 w-full rounded-lg border border-white/[0.09] bg-black/25 px-3.5 font-mono text-sm text-zinc-100 outline-none transition-colors placeholder:text-zinc-700 focus:border-violet-400/40 focus:ring-2 focus:ring-violet-400/10"
            />
          </label>
          {error && (
            <p className="mt-3 flex items-center justify-center gap-2 text-xs text-rose-300" role="alert">
              <AlertCircle className="size-3.5" aria-hidden="true" /> {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || secret.length < 32}
            className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 text-sm font-medium text-white shadow-[0_8px_24px_rgb(124_58_237/0.2)] transition-colors hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300"
          >
            {busy ? <LoaderCircle className="size-4 animate-spin" /> : <UnlockKeyhole className="size-4" />}
            {busy ? "Unlocking…" : "Unlock playground"}
          </button>
          <p className="mt-4 flex items-center justify-center gap-2 font-mono text-[10px] uppercase tracking-[0.11em] text-zinc-700">
            <ShieldCheck className="size-3" /> Local session · 30 minute expiry
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

export function GatewayPlayground({ activeModels }: { activeModels: ActiveModel[] }) {
  const [session, setSession] = useState<SessionState>("checking");
  const [workload, setWorkload] = useState<Workload>("pr_summary");
  const [model, setModel] = useState("italix-auto");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<InferenceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/operator/session", { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json().catch(() => null) as { authenticated?: boolean } | null;
        if (active) setSession(response.ok && body?.authenticated ? "unlocked" : "locked");
      })
      .catch(() => { if (active) setSession("locked"); });
    return () => { active = false; };
  }, []);

  const availableModels = useMemo(() => [
    { id: "italix-auto", kind: "router" },
    ...activeModels.filter((item) => item.workload === workload).map((item) => ({ id: item.id, kind: item.kind })),
  ], [activeModels, workload]);
  const activeRoute = activeModels.find((item) => item.workload === workload);

  function updateWorkload(value: string) {
    setWorkload(value as Workload);
    setModel("italix-auto");
    setResult(null);
    setError(null);
  }

  async function generate() {
    const content = prompt.trim();
    if (!content) {
      setError("Enter a prompt or load the safe sample diff.");
      textarea.current?.focus();
      return;
    }
    if (content.length > 20_000) {
      setError("Prompt must be 20,000 characters or fewer.");
      return;
    }
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/operator/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          workload,
          messages: [{ role: "user", content }],
          max_tokens: 320,
          temperature: 0,
          stream: false,
          allow_cloud: false,
          capture: false,
        }),
      });
      const body: unknown = await response.json().catch(() => null);
      if (response.status === 401) {
        setSession("locked");
        setPrompt("");
        setError("Your operator session expired. Unlock the playground again.");
        return;
      }
      if (!response.ok) {
        const detail = body && typeof body === "object" && "detail" in body ? String((body as { detail: unknown }).detail) : `Gateway returned HTTP ${response.status}.`;
        setError(detail);
        return;
      }
      const parsed = parseResponse(body, response.headers.get("x-italix-latency-ms"));
      if (!parsed) {
        setError("The gateway returned an unexpected response shape.");
        return;
      }
      setResult(parsed);
    } catch {
      setError("The local gateway is unavailable.");
    } finally {
      setGenerating(false);
    }
  }

  async function logout() {
    await fetch("/api/operator/session", { method: "DELETE" }).catch(() => undefined);
    setPrompt("");
    setResult(null);
    setError(null);
    setSession("locked");
  }

  function handlePromptKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (!generating) void generate();
    }
  }

  async function copyOutput() {
    if (!result) return;
    await navigator.clipboard.writeText(result.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (session === "checking") {
    return (
      <Card className="border-white/[0.07] bg-[#0d0d11]/82">
        <CardContent className="grid min-h-[25rem] place-items-center text-center">
          <div><LoaderCircle className="mx-auto size-5 animate-spin text-violet-400" /><p className="mt-3 text-xs text-zinc-600">Checking operator session…</p></div>
        </CardContent>
      </Card>
    );
  }
  if (session === "locked") return <OperatorUnlock onUnlocked={() => setSession("unlocked")} />;

  const validationValid = result?.validation && typeof result.validation.valid === "boolean" ? result.validation.valid : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-xl border border-emerald-400/[0.11] bg-emerald-400/[0.035] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300"><UnlockKeyhole className="size-3.5" /></div>
          <div className="min-w-0"><p className="text-xs font-medium text-emerald-200">Operator session unlocked</p><p className="mt-0.5 text-[10px] text-zinc-600">Cloud off · capture off · prompts held in memory only</p></div>
        </div>
        <button type="button" onClick={logout} className="flex h-8 items-center justify-center gap-2 rounded-lg border border-white/[0.07] px-3 text-[11px] text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60">
          <LogOut className="size-3.5" /> Lock session
        </button>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.02fr)_minmax(0,0.98fr)]">
        <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/86 py-0">
          <CardHeader className="border-b border-white/[0.055] p-5">
            <div className="flex items-center justify-between gap-4">
              <div><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><TerminalSquare className="size-4 text-violet-400" /> Request</CardTitle><p className="mt-1 text-xs text-zinc-600">Configure a bounded local inference</p></div>
              <Badge variant="outline" className="border-emerald-400/15 bg-emerald-400/[0.05] text-emerald-300"><ShieldCheck /> Local only</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5 p-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Workload" value={workload} onChange={updateWorkload}>
                <option value="pr_summary">pr_summary</option>
                <option value="change_triage">change_triage</option>
              </SelectField>
              <SelectField label="Model route" value={model} onChange={setModel}>
                {availableModels.map((item) => <option key={item.id} value={item.id}>{item.id}{item.kind === "router" ? " · automatic" : ""}</option>)}
              </SelectField>
            </div>

            <div className="rounded-lg border border-white/[0.06] bg-black/15 px-3.5 py-3">
              <div className="flex items-start gap-2.5"><Route className="mt-0.5 size-3.5 shrink-0 text-violet-400" /><div className="min-w-0"><p className="text-[10px] uppercase tracking-[0.12em] text-zinc-600">Active workload route</p><p className="mt-1 break-all font-mono text-[11px] text-zinc-300">{activeRoute ? `${activeRoute.id} · ${activeRoute.kind}` : "No active route reported"}</p></div></div>
            </div>

            <label className="block">
              <span className="mb-2 flex items-center justify-between gap-3"><span className="text-[10px] font-medium uppercase tracking-[0.13em] text-zinc-600">Prompt or Git diff</span><span className="font-mono text-[10px] text-zinc-700">{prompt.length.toLocaleString()} / 20,000</span></span>
              <textarea
                ref={textarea}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={handlePromptKeyDown}
                maxLength={20_000}
                spellCheck={false}
                placeholder="Paste a sanitized Git diff or developer task…"
                className="min-h-[22rem] w-full resize-y rounded-xl border border-white/[0.08] bg-[#08080b] p-4 font-mono text-[12px] leading-6 text-zinc-300 outline-none transition-colors placeholder:text-zinc-700 focus:border-violet-400/35 focus:ring-2 focus:ring-violet-400/10"
              />
            </label>

            {error && <p className="flex items-start gap-2 rounded-lg border border-rose-400/10 bg-rose-400/[0.04] px-3 py-2.5 text-xs leading-5 text-rose-300" role="alert"><AlertCircle className="mt-0.5 size-3.5 shrink-0" />{error}</p>}

            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
              <button type="button" onClick={() => { setPrompt(SAMPLE_DIFF); setWorkload("pr_summary"); setModel("italix-auto"); setResult(null); setError(null); textarea.current?.focus(); }} className="flex h-10 items-center justify-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 text-xs text-zinc-400 transition-colors hover:bg-white/[0.05] hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60"><FileDiff className="size-3.5" /> Load safe sample</button>
              <button type="button" onClick={() => void generate()} disabled={generating || !prompt.trim()} className="flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-500 px-5 text-xs font-medium text-white shadow-[0_8px_24px_rgb(124_58_237/0.18)] transition-colors hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300">
                {generating ? <LoaderCircle className="size-4 animate-spin" /> : <Play className="size-3.5 fill-current" />}{generating ? "Generating…" : "Generate"}<kbd className="ml-1 hidden rounded border border-white/15 bg-black/10 px-1.5 py-0.5 font-mono text-[9px] text-violet-100/70 sm:inline">⌘ ↵</kbd>
              </button>
            </div>
          </CardContent>
        </Card>

        <Card className="min-w-0 gap-0 border-white/[0.07] bg-[#0d0d11]/86 py-0">
          <CardHeader className="border-b border-white/[0.055] p-5">
            <div className="flex items-center justify-between gap-4"><div><CardTitle className="flex items-center gap-2 text-sm text-zinc-200"><Sparkles className="size-4 text-violet-400" /> Response</CardTitle><p className="mt-1 text-xs text-zinc-600">Exact gateway output and execution evidence</p></div>{result && <button type="button" onClick={() => void copyOutput()} className="grid size-8 place-items-center rounded-lg border border-white/[0.07] text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60" aria-label="Copy response"><Copy className="size-3.5" /></button>}</div>
          </CardHeader>
          <CardContent className="flex min-h-[42rem] flex-col p-5">
            {generating ? (
              <div className="flex flex-1 flex-col"><div className="flex items-center gap-2 text-xs text-violet-300"><LoaderCircle className="size-3.5 animate-spin" /> Routing local request…</div><div className="mt-6 space-y-3">{["w-4/5", "w-full", "w-3/4", "w-5/6"].map((width) => <div key={width} className={cn("h-3 animate-pulse rounded bg-white/[0.045]", width)} />)}</div></div>
            ) : result ? (
              <>
                <div className="flex flex-wrap gap-2">
                  {result.abstained ? <Badge variant="outline" className="border-amber-400/15 bg-amber-400/[0.06] text-amber-300"><CircleStop /> Abstained</Badge> : <Badge variant="outline" className="border-emerald-400/15 bg-emerald-400/[0.05] text-emerald-300"><CheckCircle2 /> Completed</Badge>}
                  {validationValid !== null && <Badge variant="outline" className={validationValid ? "border-emerald-400/15 text-emerald-300" : "border-rose-400/15 text-rose-300"}>{validationValid ? "Validation passed" : "Validation failed"}</Badge>}
                  {copied && <span className="self-center text-[10px] text-zinc-500">Copied</span>}
                </div>
                <pre data-testid="response-output" className="mt-5 min-h-64 flex-1 whitespace-pre-wrap break-words rounded-xl border border-white/[0.065] bg-[#08080b] p-4 font-sans text-[13px] leading-6 text-zinc-300">{result.content}</pre>
                {result.abstentionReasons.length > 0 && <div className="mt-3 rounded-lg border border-amber-400/10 bg-amber-400/[0.035] px-3 py-2.5"><p className="text-[10px] uppercase tracking-[0.12em] text-amber-300">Abstention evidence</p><ul className="mt-1.5 space-y-1 text-xs text-zinc-500">{result.abstentionReasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></div>}
                <div className="mt-4 grid gap-3 rounded-xl border border-white/[0.06] bg-black/15 p-4 sm:grid-cols-2">
                  <div><p className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.11em] text-zinc-700"><Code2 className="size-3" /> Model ID</p><p data-testid="response-model" className="mt-1.5 break-all font-mono text-[11px] text-zinc-300">{result.registryModel}</p></div>
                  <div><p className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.11em] text-zinc-700"><Route className="size-3" /> Route</p><p data-testid="response-route" className="mt-1.5 font-mono text-[11px] text-zinc-300">{result.route}</p></div>
                  <div><p className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.11em] text-zinc-700"><Clock3 className="size-3" /> Backend latency</p><p data-testid="response-latency" className="mt-1.5 font-mono text-[11px] text-zinc-300">{result.latencyMs === "Unavailable" ? result.latencyMs : `${result.latencyMs} ms`}</p></div>
                  <div><p className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.11em] text-zinc-700"><Fingerprint className="size-3" /> Trace ID</p><p data-testid="response-trace" className="mt-1.5 break-all font-mono text-[11px] text-zinc-300">{result.traceId}</p></div>
                </div>
              </>
            ) : (
              <div className="grid flex-1 place-items-center text-center"><div className="max-w-xs"><div className="mx-auto grid size-12 place-items-center rounded-xl border border-white/[0.07] bg-white/[0.02] text-zinc-600"><Binary className="size-5" /></div><h3 className="mt-4 text-sm font-medium text-zinc-300">Awaiting a local request</h3><p className="mt-2 text-xs leading-5 text-zinc-600">Select a workload, provide sanitized input, and generate to inspect the exact gateway response.</p></div></div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
