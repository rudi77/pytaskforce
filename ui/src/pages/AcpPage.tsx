import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function AcpPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>ACP Peers</CardTitle>
        <CardDescription>
          Peer registration and connectivity tests are part of Phase 6.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          Coming in Phase 6.
        </div>
      </CardContent>
    </Card>
  );
}
