import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/api/client";

interface ForbiddenNoticeProps {
  /** Error returned by the underlying query. */
  error: unknown;
  /** Short label of what the user was trying to access (e.g. "LLM provider settings"). */
  area: string;
}

export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}

export default function ForbiddenNotice({ error, area }: ForbiddenNoticeProps) {
  const message =
    error instanceof Error ? error.message : "Permission denied.";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Admin access required</CardTitle>
        <CardDescription>
          Your account doesn't have the
          <code className="mx-1">tenant:manage</code>permission required to view or edit
          {` ${area}`}. Ask a tenant administrator to assign you the admin role.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{message}</CardContent>
    </Card>
  );
}
