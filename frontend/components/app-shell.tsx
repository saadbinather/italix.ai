"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BrainCircuit,
  ChartNoAxesCombined,
  ChevronRight,
  CircleGauge,
  FlaskConical,
  GalleryVerticalEnd,
  Menu,
  MemoryStick,
  ServerCog,
  Sparkles,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

const navigation = [
  { label: "Overview", icon: CircleGauge, href: "/" },
  { label: "AI Gateway", icon: BrainCircuit, href: "/gateway" },
  { label: "Learning Studio", icon: Sparkles, href: "/learning" },
  { label: "Evaluations", icon: FlaskConical },
  { label: "Model Registry", icon: ServerCog },
  { label: "Usage & Costs", icon: ChartNoAxesCombined },
  { label: "Developer Memory", icon: MemoryStick },
  { label: "Demo", icon: GalleryVerticalEnd },
] as const;

function Brand() {
  return (
    <div className="flex h-9 items-center gap-3 px-1">
      <div className="relative grid size-8 place-items-center rounded-[10px] border border-violet-400/25 bg-violet-500/[0.09] shadow-[inset_0_1px_0_rgb(255_255_255/0.06),0_0_24px_rgb(124_58_237/0.08)]">
        <div className="size-2.5 rotate-45 rounded-[3px] border border-violet-300/80 bg-violet-400/30" />
        <div className="absolute inset-[5px] rounded-[7px] border border-violet-400/10" />
      </div>
      <div className="leading-none">
        <span className="text-[15px] font-semibold tracking-[-0.025em] text-zinc-50">
          ITALIX
        </span>
        <span className="text-[15px] font-semibold text-violet-400">.ai</span>
      </div>
    </div>
  );
}

function SidebarContent({ close, pathname }: { close?: () => void; pathname: string }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between border-b border-white/[0.065] px-4">
        <Brand />
        {close ? (
          <button
            type="button"
            onClick={close}
            className="grid size-8 place-items-center rounded-md text-zinc-500 transition-colors hover:bg-white/[0.05] hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/70"
            aria-label="Close navigation"
          >
            <X className="size-4" />
          </button>
        ) : <span className="rounded border border-white/[0.06] px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-[0.12em] text-zinc-600">Local</span>}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-5" aria-label="Primary navigation">
        <p className="mb-2 px-3 font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600">
          Workspace
        </p>
        <ul className="space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = "href" in item && item.href === pathname;
            return (
              <li key={item.label}>
                {"href" in item ? (
                  <Link
                    href={item.href}
                    onClick={close}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex h-9 items-center gap-3 rounded-lg border px-3 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/70",
                      active
                        ? "border-violet-400/[0.12] bg-violet-400/[0.08] text-zinc-100 shadow-[inset_0_1px_0_rgb(255_255_255/0.025)]"
                        : "border-transparent text-zinc-500 hover:bg-white/[0.035] hover:text-zinc-300",
                    )}
                  >
                    {active && <span className="absolute inset-y-2 left-0 w-px rounded-full bg-violet-400" />}
                    <Icon className={cn("size-4", active ? "text-violet-300" : "text-zinc-600 group-hover:text-zinc-400")} aria-hidden="true" />
                    <span className="whitespace-nowrap">{item.label}</span>
                    {active && <ChevronRight className="ml-auto size-3.5 text-violet-300/50" />}
                  </Link>
                ) : (
                  <button
                    type="button"
                    disabled
                    aria-disabled="true"
                    title={`${item.label} — Coming soon`}
                    className="flex h-9 w-full cursor-not-allowed items-center gap-3 rounded-lg px-3 text-left text-[13px] text-zinc-500 opacity-75"
                  >
                    <Icon className="size-4 text-zinc-600" aria-hidden="true" />
                    <span className="whitespace-nowrap">{item.label}</span>
                    <span className="ml-auto rounded border border-white/[0.06] px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider text-zinc-600">
                      Soon
                    </span>
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-white/[0.065] p-3">
        <div className="rounded-lg border border-white/[0.055] bg-white/[0.018] p-3">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Activity className="size-3.5 text-violet-400" aria-hidden="true" />
            Local workspace
          </div>
          <p className="mt-1.5 font-mono text-[10px] text-zinc-600">127.0.0.1 · private</p>
        </div>
      </div>
    </div>
  );
}

export function AppShell({
  connected,
  children,
}: {
  connected: boolean;
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const openButton = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  const page = pathname === "/gateway"
    ? { title: "AI Gateway", subtitle: "Local inference playground" }
    : pathname === "/learning"
      ? { title: "Learning Studio", subtitle: "Specialist training progress" }
      : { title: "Overview", subtitle: "Infrastructure health and routing" };

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        openButton.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  return (
    <div className="min-h-screen bg-[#08080a] text-zinc-100 selection:bg-violet-500/30">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 shrink-0 border-r border-white/[0.065] bg-[#0b0b0e]/95 backdrop-blur-xl lg:block">
        <SidebarContent pathname={pathname} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/75 backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation backdrop"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="relative h-full w-[min(20rem,86vw)] border-r border-white/[0.08] bg-[#0b0b0e] shadow-2xl motion-safe:animate-in motion-safe:slide-in-from-left motion-safe:duration-200"
          >
            <SidebarContent close={() => setMobileOpen(false)} pathname={pathname} />
          </aside>
        </div>
      )}

      <div className="min-h-screen min-w-0 overflow-x-hidden lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center border-b border-white/[0.065] bg-[#09090b]/82 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <button
            ref={openButton}
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            className="mr-3 grid size-9 place-items-center rounded-lg border border-white/[0.07] bg-white/[0.025] text-zinc-400 transition-colors hover:bg-white/[0.055] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/70 lg:hidden"
          >
            <Menu className="size-4" />
          </button>

          <div>
            <h1 className="text-sm font-medium tracking-[-0.015em] text-zinc-100">{page.title}</h1>
            <p className="hidden text-[11px] text-zinc-600 sm:block">{page.subtitle}</p>
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            <div
              className={cn(
                "flex h-8 items-center gap-2 rounded-lg border px-2.5 text-[11px] font-medium",
                connected
                  ? "border-emerald-400/[0.14] bg-emerald-400/[0.055] text-emerald-300"
                  : "border-amber-400/[0.14] bg-amber-400/[0.055] text-amber-300",
              )}
              role="status"
            >
              <span className="relative flex size-1.5">
                {connected && (
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                )}
                <span
                  className={cn(
                    "relative inline-flex size-1.5 rounded-full",
                    connected ? "bg-emerald-400" : "bg-amber-400",
                  )}
                />
              </span>
              <span className="hidden sm:inline">{connected ? "Backend connected" : "Backend unavailable"}</span>
              <span className="sm:hidden">{connected ? "Online" : "Offline"}</span>
            </div>
          </div>
        </header>

        <main className="relative min-w-0 overflow-x-hidden px-4 py-8 sm:px-6 lg:px-8 lg:py-9 xl:px-10">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden">
            <div className="absolute -top-40 left-1/4 h-80 w-80 rounded-full bg-violet-700/[0.055] blur-3xl" />
          </div>
          <div className="relative motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-500">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
