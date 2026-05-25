import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@taskforce/ui-shell";
import { Button, Field, Input } from "@fluentui/react-components";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSettings } from "@/lib/settings";

interface LoginResponse {
  access_token: string;
  token_type: string;
}

interface LocationState {
  from?: { pathname?: string };
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const setApiToken = useSettings((s) => s.setApiToken);

  const [tenantId, setTenantId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await apiFetch<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        body: { tenant_id: tenantId, email, password },
      });
      setApiToken(response.access_token);
      await queryClient.invalidateQueries({ queryKey: ["ui-manifest"] });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Falsche Credentials.");
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Login fehlgeschlagen.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      {/* Card primitive stays shadcn for now — Fluent's Card is slot-based
       *  and would require restructuring CardHeader/Title/Description/Content.
       *  Handled in a dedicated primitive migration. */}
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Authenticate against the Taskforce backend to access the management UI.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <Field label="Tenant">
              <Input
                id="tenant_id"
                autoComplete="organization"
                value={tenantId}
                onChange={(_, data) => setTenantId(data.value)}
                disabled={submitting}
                required
              />
            </Field>
            <Field label="Email">
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(_, data) => setEmail(data.value)}
                disabled={submitting}
                required
              />
            </Field>
            <Field label="Password">
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(_, data) => setPassword(data.value)}
                disabled={submitting}
                required
              />
            </Field>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <Button
              type="submit"
              appearance="primary"
              className="w-full"
              disabled={submitting}
            >
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              No tenant yet?{" "}
              <a
                href="/signup"
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Create one
              </a>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
