import { useState } from "react";
import { Network, Pencil, PlugZap, Plus, Trash2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  useAcpPeers,
  useCreateAcpPeer,
  useDeleteAcpPeer,
  useTestAcpPeer,
  useUpdateAcpPeer,
  type AcpPeer,
  type AcpPeerInput,
  type AcpTestResult,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import { AcpPeerDialog } from "@/features/acp/AcpPeerDialog";

interface DialogState {
  open: boolean;
  mode: "create" | "edit";
  peer: AcpPeer | null;
}

export default function AcpPage() {
  const peers = useAcpPeers();
  const createMutation = useCreateAcpPeer();
  const updateMutation = useUpdateAcpPeer();
  const deleteMutation = useDeleteAcpPeer();
  const testMutation = useTestAcpPeer();
  const [dialog, setDialog] = useState<DialogState>({
    open: false,
    mode: "create",
    peer: null,
  });
  const [testResult, setTestResult] = useState<
    Record<string, AcpTestResult | { ok: false; error: string; latency_ms: 0 }>
  >({});

  const onSubmit = async (payload: AcpPeerInput) => {
    if (dialog.mode === "create") {
      await createMutation.mutateAsync(payload);
      toast.success("Peer registered", payload.name);
    } else if (dialog.peer) {
      await updateMutation.mutateAsync({
        name: dialog.peer.name,
        payload: {
          base_url: payload.base_url,
          agent: payload.agent,
          description: payload.description ?? "",
          auth: payload.auth,
        },
      });
      toast.success("Peer updated", payload.name);
    }
  };

  const onDelete = async (peer: AcpPeer) => {
    if (!window.confirm(`Delete ACP peer "${peer.name}"?`)) return;
    try {
      await deleteMutation.mutateAsync(peer.name);
      toast.success("Peer deleted", peer.name);
    } catch (err) {
      toast.error(
        "Delete failed",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  const onTest = async (peer: AcpPeer) => {
    try {
      const result = await testMutation.mutateAsync(peer.name);
      setTestResult((prev) => ({ ...prev, [peer.name]: result }));
      if (result.ok) {
        toast.success(
          `${peer.name} reachable`,
          `${result.status_code ?? "?"} · ${result.latency_ms} ms`,
        );
      } else {
        toast.warning(`${peer.name} unreachable`, result.error ?? "no response");
      }
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : (err as Error).message;
      setTestResult((prev) => ({
        ...prev,
        [peer.name]: { ok: false, error: message, latency_ms: 0 },
      }));
      toast.error(`${peer.name} test failed`, message);
    }
  };

  const items = peers.data ?? [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Network className="h-5 w-5" />
              ACP Peers
            </CardTitle>
            <CardDescription>
              Remote agents reachable over the Agent Communication Protocol.
              Persisted in <code>.taskforce/acp_peers.json</code>.
            </CardDescription>
          </div>
          <Button onClick={() => setDialog({ open: true, mode: "create", peer: null })}>
            <Plus className="h-4 w-4" />
            Add peer
          </Button>
        </CardHeader>
        <CardContent>
          {peers.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : peers.error ? (
            <EmptyState
              title="Could not load peers"
              description={
                peers.error instanceof ApiError
                  ? peers.error.message
                  : "Backend returned an error."
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="No peers registered"
              description="Add a peer so this agent can call remote ACP-enabled agents."
              action={
                <Button onClick={() => setDialog({ open: true, mode: "create", peer: null })}>
                  <Plus className="h-4 w-4" />
                  Add peer
                </Button>
              }
            />
          ) : (
            <ul className="space-y-3">
              {items.map((peer) => (
                <li
                  key={peer.name}
                  className="rounded-md border border-border bg-card/30 p-3"
                >
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{peer.name}</span>
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {peer.auth_type}
                        </Badge>
                        {peer.token_env ? (
                          <Badge variant="secondary" className="text-[10px]">
                            env:{peer.token_env}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        {peer.base_url} · agent={peer.agent}
                      </p>
                      {peer.description ? (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {peer.description}
                        </p>
                      ) : null}
                      <TestResultLine result={testResult[peer.name]} />
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onTest(peer)}
                        disabled={testMutation.isPending}
                      >
                        <PlugZap className="h-3.5 w-3.5" />
                        Test
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setDialog({ open: true, mode: "edit", peer })
                        }
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => onDelete(peer)}
                        disabled={deleteMutation.isPending}
                        aria-label="Delete peer"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <AcpPeerDialog
        open={dialog.open}
        mode={dialog.mode}
        initial={dialog.peer}
        onClose={() => setDialog((d) => ({ ...d, open: false }))}
        onSubmit={onSubmit}
      />
    </div>
  );
}

function TestResultLine({
  result,
}: {
  result: AcpTestResult | { ok: false; error: string; latency_ms: 0 } | undefined;
}) {
  if (!result) return null;
  if (result.ok) {
    return (
      <p className="mt-1 text-xs text-success">
        ✓ Reachable · {result.status_code ?? "?"} · {result.latency_ms} ms
      </p>
    );
  }
  return (
    <p className="mt-1 text-xs text-destructive">
      ✗ {result.error ?? "unreachable"}
    </p>
  );
}
