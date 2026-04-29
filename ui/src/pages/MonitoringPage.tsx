import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function MonitoringPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Monitoring</CardTitle>
        <CardDescription>
          Token-usage charts and live active-runs land in Phase 5.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          Coming in Phase 5.
        </div>
      </CardContent>
    </Card>
  );
}
