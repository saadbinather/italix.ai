import { Skeleton } from "@/components/ui/skeleton";

export function AppShellSkeleton() {
  return (
    <div className="min-h-screen bg-[#08080a] text-zinc-100">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/[0.07] bg-[#0b0b0e] p-5 lg:block">
        <Skeleton className="h-9 w-32" />
        <div className="mt-10 space-y-3">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="h-16 border-b border-white/[0.07] px-6 py-4">
          <Skeleton className="h-6 w-32" />
        </header>
        <main className="mx-auto max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="mt-5 h-9 w-80 max-w-full" />
          <Skeleton className="mt-4 h-5 w-[34rem] max-w-full" />
          <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-36 w-full rounded-xl" />
            ))}
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Skeleton className="h-80 w-full rounded-xl" />
            <Skeleton className="h-80 w-full rounded-xl" />
          </div>
          <Skeleton className="mt-4 h-64 w-full rounded-xl" />
        </main>
      </div>
    </div>
  );
}
