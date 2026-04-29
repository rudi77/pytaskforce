import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/FormField";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/api/client";
import type { AcpPeer, AcpPeerInput } from "@/api/queries";

interface Props {
  open: boolean;
  mode: "create" | "edit";
  initial?: AcpPeer | null;
  onClose: () => void;
  onSubmit: (payload: AcpPeerInput) => Promise<void>;
}

export function AcpPeerDialog({ open, mode, initial, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [agent, setAgent] = useState("");
  const [description, setDescription] = useState("");
  const [authType, setAuthType] = useState<"none" | "bearer" | "mtls">("none");
  const [tokenEnv, setTokenEnv] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (initial && mode === "edit") {
      setName(initial.name);
      setBaseUrl(initial.base_url);
      setAgent(initial.agent);
      setDescription(initial.description ?? "");
      setAuthType((initial.auth_type as "none" | "bearer" | "mtls") ?? "none");
      setTokenEnv(initial.token_env ?? "");
      setToken("");
    } else {
      setName("");
      setBaseUrl("");
      setAgent("");
      setDescription("");
      setAuthType("none");
      setTokenEnv("");
      setToken("");
    }
    setError(null);
    setBusy(false);
  }, [open, initial, mode]);

  const submit = async () => {
    setError(null);
    if (!name || !baseUrl || !agent) {
      setError("Name, base URL and agent are required.");
      return;
    }
    if (authType === "bearer" && !tokenEnv && !token) {
      setError("Bearer auth needs a token_env or a literal token.");
      return;
    }
    setBusy(true);
    try {
      const payload: AcpPeerInput = {
        name,
        base_url: baseUrl,
        agent,
        description,
        auth:
          authType === "bearer"
            ? {
                type: "bearer",
                token_env: tokenEnv || null,
                token: token || null,
              }
            : { type: authType },
      };
      await onSubmit(payload);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => (value ? null : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Register ACP peer" : `Edit ${initial?.name ?? ""}`}
          </DialogTitle>
          <DialogDescription>
            Persisted to <code>.taskforce/acp_peers.json</code>. Bearer tokens
            should usually live in an environment variable referenced via
            <code className="ml-1">token_env</code>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <FormField label="Name" htmlFor="acp-name" required>
            <Input
              id="acp-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="remote-butler"
              disabled={mode === "edit"}
              autoComplete="off"
            />
          </FormField>
          <FormField label="Base URL" htmlFor="acp-url" required>
            <Input
              id="acp-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://remote.taskforce:8800"
            />
          </FormField>
          <FormField label="Remote agent" htmlFor="acp-agent" required>
            <Input
              id="acp-agent"
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              placeholder="butler"
            />
          </FormField>
          <FormField label="Description" htmlFor="acp-desc">
            <Textarea
              id="acp-desc"
              rows={2}
              className="font-sans"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormField>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Auth type" htmlFor="acp-auth-type">
              <select
                id="acp-auth-type"
                value={authType}
                onChange={(e) =>
                  setAuthType(e.target.value as "none" | "bearer" | "mtls")
                }
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              >
                <option value="none">none</option>
                <option value="bearer">bearer</option>
                <option value="mtls">mTLS</option>
              </select>
            </FormField>
            {authType === "bearer" ? (
              <FormField label="Token env var" htmlFor="acp-token-env">
                <Input
                  id="acp-token-env"
                  value={tokenEnv}
                  onChange={(e) => setTokenEnv(e.target.value)}
                  placeholder="REMOTE_BUTLER_TOKEN"
                />
              </FormField>
            ) : null}
          </div>
          {authType === "bearer" ? (
            <FormField
              label="Literal token (optional)"
              htmlFor="acp-token"
              description="Avoid storing tokens here — prefer the env var."
            >
              <Input
                id="acp-token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </FormField>
          ) : null}

          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={busy}>
            {mode === "create" ? "Register" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
