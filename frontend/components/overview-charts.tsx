"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartDatum {
  name: string;
  value: number;
  color: string;
}

const tooltipStyle = {
  background: "#111116",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 10,
  boxShadow: "0 18px 45px rgba(0,0,0,0.35)",
  color: "#e4e4e7",
  fontSize: 12,
};

export function RequestDistributionChart({ data }: { data: ChartDatum[] }) {
  return (
    <div className="grid min-h-56 min-w-0 grid-cols-1 items-center gap-2 sm:grid-cols-[minmax(0,1fr)_8.5rem]" aria-label="Request distribution chart">
      <div className="h-56 min-w-0">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="61%"
              outerRadius="84%"
              paddingAngle={data.length > 1 ? 3 : 0}
              stroke="transparent"
              isAnimationActive={false}
            >
              {data.map((item) => (
                <Cell key={item.name} fill={item.color} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} cursor={false} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:block sm:space-y-3">
        {data.map((item) => (
          <div key={item.name} className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="truncate text-[11px] text-zinc-500">{item.name}</span>
            </div>
            <p className="mt-0.5 pl-3.5 font-mono text-sm font-medium text-zinc-200">
              {item.value.toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LatencyComparisonChart({ data }: { data: ChartDatum[] }) {
  return (
    <div className="h-56 w-full min-w-0" aria-label="Average latency comparison chart">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.055)" />
          <XAxis
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            dy={8}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#52525b", fontSize: 10 }}
            width={52}
            tickFormatter={(value: number) => `${value >= 1000 ? `${(value / 1000).toFixed(1)}k` : Math.round(value)}ms`}
          />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(139,92,246,0.05)" }} />
          <Bar dataKey="value" name="Average latency (ms)" radius={[5, 5, 2, 2]} maxBarSize={54} isAnimationActive={false}>
            {data.map((item) => (
              <Cell key={item.name} fill={item.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
