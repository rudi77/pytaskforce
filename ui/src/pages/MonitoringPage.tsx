import { useMemo, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Coins, TrendingUp } from "lucide-react";

import { useCostSummary, useTokenUsage } from "@/api/queries";
import { KpiCard, formatTokens, formatUsd } from "@/features/monitoring/KpiCard";
import { TokenUsageChart } from "@/features/monitoring/TokenUsageChart";
import { AgentCostChart } from "@/features/monitoring/AgentCostChart";
import { ModelDistributionChart } from "@/features/monitoring/ModelDistributionChart";
import { ActiveRunsTable } from "@/features/monitoring/ActiveRunsTable";
import { cn } from "@/lib/utils";

type Range = "today" | "7d" | "30d";
type Granularity = "hour" | "day";

const RANGES: { id: Range; label: string; granularity: Granularity }[] = [
  { id: "today", label: "Today", granularity: "hour" },
  { id: "7d", label: "7 days", granularity: "day" },
  { id: "30d", label: "30 days", granularity: "day" },
];

function rangeStart(range: Range): string {
  const now = new Date();
  const start = new Date(now);
  if (range === "today") {
    start.setHours(0, 0, 0, 0);
  } else if (range === "7d") {
    start.setDate(start.getDate() - 7);
  } else {
    start.setDate(start.getDate() - 30);
  }
  return start.toISOString();
}

export default function MonitoringPage() {
  const [range, setRange] = useState<Range>("today");
  const rangeDef = RANGES.find((r) => r.id === range)!;
  const fromIso = useMemo(() => rangeStart(range), [range]);
  const tokenUsage = useTokenUsage({ granularity: rangeDef.granularity, from: fromIso });
  const costSummary = useCostSummary();

  const tokensInRange = useMemo(() => {
    if (!tokenUsage.data) return 0;
    return tokenUsage.data.buckets.reduce(
      (acc, b) => acc + b.prompt_tokens + b.completion_tokens,
      0,
    );
  }, [tokenUsage.data]);

  const costInRange = useMemo(() => {
    if (!tokenUsage.data) return 0;
    return tokenUsage.data.buckets.reduce((acc, b) => acc + b.cost_usd, 0);
  }, [tokenUsage.data]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Monitoring</CardTitle>
            <CardDescription>
              Token usage, cost and live execution health.
              {costSummary.data?.pricing_as_of ? (
                <span className="ml-1 text-xs">
                  Pricing as of {costSummary.data.pricing_as_of}.
                </span>
              ) : null}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-1 rounded-md bg-muted p-1">
            {RANGES.map((r) => (
              <Button
                key={r.id}
                variant="ghost"
                size="sm"
                onClick={() => setRange(r.id)}
                className={cn(
                  "h-7 px-3 text-xs",
                  r.id === range ? "bg-background shadow-sm" : "",
                )}
              >
                {r.label}
              </Button>
            ))}
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Tokens"
          value={formatTokens(tokensInRange)}
          hint={rangeDef.label.toLowerCase()}
          icon={TrendingUp}
          loading={tokenUsage.isLoading}
        />
        <KpiCard
          label="Cost"
          value={formatUsd(costInRange)}
          hint={`approx. via ${rangeDef.granularity}-buckets`}
          icon={Coins}
          loading={tokenUsage.isLoading}
        />
        <KpiCard
          label="LLM calls"
          value={String(tokenUsage.data?.buckets.reduce((a, b) => a + b.call_count, 0) ?? 0)}
          hint={rangeDef.label.toLowerCase()}
          icon={TrendingUp}
          loading={tokenUsage.isLoading}
        />
        <KpiCard
          label="Cost (today)"
          value={formatUsd(costSummary.data?.today_usd ?? 0)}
          hint="rolling"
          icon={Coins}
          loading={costSummary.isLoading}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Token usage</CardTitle>
          <CardDescription>
            Stacked prompt vs. completion · {rangeDef.granularity}-buckets
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TokenUsageChart buckets={tokenUsage.data?.buckets ?? []} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Cost per agent</CardTitle>
            <CardDescription>Last 30 days · Top 10</CardDescription>
          </CardHeader>
          <CardContent>
            <AgentCostChart entries={costSummary.data?.by_agent ?? []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Token distribution by model</CardTitle>
            <CardDescription>Last 30 days · total tokens</CardDescription>
          </CardHeader>
          <CardContent>
            <ModelDistributionChart entries={costSummary.data?.by_model ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle>Active runs</CardTitle>
            <CardDescription>Refreshes every 4 seconds.</CardDescription>
          </div>
          <Badge variant="outline">live</Badge>
        </CardHeader>
        <CardContent>
          <ActiveRunsTable intervalMs={4_000} />
        </CardContent>
      </Card>
    </div>
  );
}
