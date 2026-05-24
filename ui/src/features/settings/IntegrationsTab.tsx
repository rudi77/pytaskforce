import { Badge, Button } from "@fluentui/react-components";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOAuthConnections, useRevokeOAuthConnection } from "@/api/queries";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

function formatDate(value: string | null): string {
  if (!value) return "no expiry";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function IntegrationsTab() {
  const query = useOAuthConnections();
  const revoke = useRevokeOAuthConnection();

  if (isForbiddenError(query.error)) {
    return <ForbiddenNotice error={query.error} area="OAuth connections" />;
  }

  if (query.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (query.data?.auth_manager_available === false) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>OAuth Integrations</CardTitle>
          <CardDescription>
            The auth manager is unavailable on this instance. The
            <code className="mx-1">cryptography</code>
            package ships in the core install — run <code>uv sync</code> and restart to enable
            Gmail / Calendar / Drive connections.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const connections = query.data?.connections ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>OAuth Integrations</CardTitle>
          <CardDescription>
            External accounts the framework has tokens for. To connect a new account, run the
            <code className="mx-1">authenticate</code>
            tool from chat — the device-flow walks you through it on the channel of your choice.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {connections.length === 0 ? (
            <p className="text-sm text-muted-foreground">No connections yet.</p>
          ) : (
            <ul className="space-y-2">
              {connections.map((c) => (
                <li
                  key={c.provider}
                  className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{c.provider}</span>
                      <Badge
                        color={
                          c.is_expired || c.status !== "active" ? "warning" : "success"
                        }
                      >
                        {c.is_expired ? "expired" : c.status}
                      </Badge>
                      {c.has_refresh_token ? (
                        <Badge appearance="tint" color="subtle">refreshable</Badge>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Expires: {formatDate(c.expires_at)}
                    </div>
                    {c.scopes.length ? (
                      <div className="text-xs text-muted-foreground">
                        Scopes: {c.scopes.join(", ")}
                      </div>
                    ) : null}
                  </div>
                  <Button
                    appearance="outline"
                    onClick={() => revoke.mutate(c.provider)}
                    disabled={revoke.isPending}
                  >
                    Disconnect
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
