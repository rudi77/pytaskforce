import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TokenUsageBucket } from "@/api/queries";

interface Props {
  buckets: TokenUsageBucket[];
}

export function TokenUsageChart({ buckets }: Props) {
  const data = useMemo(
    () =>
      buckets.map((b) => ({
        bucket: b.bucket,
        prompt: b.prompt_tokens,
        completion: b.completion_tokens,
      })),
    [buckets],
  );

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No usage recorded yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
        <XAxis
          dataKey="bucket"
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "hsl(var(--foreground))" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="prompt" stackId="tokens" fill="hsl(var(--primary))" name="Prompt" />
        <Bar
          dataKey="completion"
          stackId="tokens"
          fill="hsl(var(--success))"
          name="Completion"
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
