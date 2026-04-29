import { useMemo } from "react";
import { Activity, Bot, Coins, MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useActiveRuns,
  useConversations,
  useCostSummary,
  useTokenUsage,
} from "@/api/queries";
import { KpiCard, formatTokens, formatUsd } from "@/features/monitoring/KpiCard";
import { TokenUsageChart } from "@/features/monitoring/TokenUsageChart";
import { ActiveRunsTable } from "@/features/monitoring/ActiveRunsTable";

function todayIso(): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today.toISOString();
}

export default function DashboardPage() {
  const fromIso = useMemo(() => todayIso(), []);
  const tokenUsage = useTokenUsage({ granularity: "hour", from: fromIso });
  const costSummary = useCostSummary();
  const activeRuns = useActiveRuns(8_000);
  const conversations = useConversations();

  const tokensToday = useMemo(() => {
    if (!tokenUsage.data) return 0;
    return tokenUsage.data.buckets.reduce(
      (acc, b) => acc + b.prompt_tokens + b.completion_tokens,
      0,
    );
  }, [tokenUsage.data]);

  const approxBanner = costSummary.data?.pricing_as_of
    ? `Pricing as of ${costSummary.data.pricing_as_of} — values are approximate.`
    : "Pricing table missing — costs default to $1/$3 per million.";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Overview</h2>
        <p className="text-sm text-muted-foreground">{approxBanner}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Tokens today"
          value={formatTokens(tokensToday)}
          hint="prompt + completion"
          icon={Activity}
          loading={tokenUsage.isLoading}
        />
        <KpiCard
          label="Cost today"
          value={formatUsd(costSummary.data?.today_usd ?? 0)}
          hint={`week: ${formatUsd(costSummary.data?.week_usd ?? 0)}`}
          icon={Coins}
          loading={costSummary.isLoading}
        />
        <KpiCard
          label="Active runs"
          value={String(activeRuns.data?.runs.length ?? 0)}
          hint="currently executing"
          icon={Bot}
          loading={activeRuns.isLoading}
        />
        <KpiCard
          label="Conversations"
          value={String(conversations.data?.length ?? 0)}
          hint="active sessions"
          icon={MessageSquare}
          loading={conversations.isLoading}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle>Token usage today</CardTitle>
              <CardDescription>Hourly buckets · stacked prompt + completion</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/monitoring">Open monitoring →</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <TokenUsageChart buckets={tokenUsage.data?.buckets ?? []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top models</CardTitle>
            <CardDescription>Last 30 days, by cost</CardDescription>
          </CardHeader>
          <CardContent>
            {costSummary.data && costSummary.data.by_model.length > 0 ? (
              <ul className="space-y-2 text-sm">
                {costSummary.data.by_model.slice(0, 6).map((m) => (
                  <li
                    key={m.model}
                    className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                  >
                    <span className="truncate font-mono text-xs">{m.model}</span>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{formatTokens(m.total_tokens)}</span>
                      <Badge variant="outline">{formatUsd(m.cost_usd)}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No usage recorded yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle>Active runs</CardTitle>
            <CardDescription>Live snapshot · refreshes every few seconds</CardDescription>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to="/monitoring">View all →</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <ActiveRunsTable intervalMs={6_000} />
        </CardContent>
      </Card>
    </div>
  );
}
