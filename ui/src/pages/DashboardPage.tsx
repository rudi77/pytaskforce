import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, Bot, Coins, MessageSquare } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
}

function KpiCard({ label, value, hint, icon: Icon }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="pt-0">
        <div className="text-2xl font-semibold tracking-tight">{value}</div>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Overview</h2>
        <p className="text-sm text-muted-foreground">
          Live numbers will land here once Phase 5 (Monitoring + Cost) is wired up.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Tokens today" value="—" hint="prompt + completion" icon={Activity} />
        <KpiCard label="Cost today" value="—" hint="USD, approximate" icon={Coins} />
        <KpiCard label="Active runs" value="—" hint="currently executing" icon={Bot} />
        <KpiCard label="Conversations" value="—" hint="active sessions" icon={MessageSquare} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Streaming run history is part of Phase 5.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No data yet — run a mission to populate this view.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
