import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AgentUsageEntry } from "@/api/queries";
import { formatUsd } from "@/features/monitoring/KpiCard";

interface Props {
  entries: AgentUsageEntry[];
}

export function AgentCostChart({ entries }: Props) {
  const data = useMemo(
    () =>
      entries
        .slice(0, 10)
        .map((e) => ({ agent: e.agent, cost: Number(e.cost_usd.toFixed(4)) })),
    [entries],
  );

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No costs recorded.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ left: 16, right: 16 }}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
        <XAxis
          type="number"
          tickFormatter={(v) => formatUsd(v)}
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
        />
        <YAxis
          type="category"
          dataKey="agent"
          width={120}
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(value) => formatUsd(typeof value === "number" ? value : Number(value) || 0)}
        />
        <Bar dataKey="cost" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
