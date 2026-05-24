import { useState } from "react";
import {
  Add20Regular,
  Delete20Regular,
  Edit20Regular,
  PlugConnected20Regular,
  PlugConnectedCheckmark20Regular,
} from "@fluentui/react-icons";
import { Badge, Button } from "@fluentui/react-components";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { useCurrentPermissions } from "@/lib/permissions";

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
  const permissions = useCurrentPermissions();
  const canManagePeers = permissions.can("system:config");
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
              <PlugConnected20Regular />
              ACP Peers
            </CardTitle>
            <CardDescription>
              Remote agents reachable over the Agent Communication Protocol.
              Persisted in <code>.taskforce/acp_peers.json</code>.
            </CardDescription>
          </div>
          {canManagePeers ? (
            <Button
              appearance="primary"
              icon={<Add20Regular />}
              onClick={() => setDialog({ open: true, mode: "create", peer: null })}
            >
              Add peer
            </Button>
          ) : null}
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
                canManagePeers ? (
                  <Button
                    appearance="primary"
                    icon={<Add20Regular />}
                    onClick={() => setDialog({ open: true, mode: "create", peer: null })}
                  >
                    Add peer
                  </Button>
                ) : undefined
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
                        <Badge appearance="outline" color="subtle" className="font-mono text-[10px]">
                          {peer.auth_type}
                        </Badge>
                        {peer.token_env ? (
                          <Badge appearance="tint" color="subtle" className="text-[10px]">
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
                        appearance="outline"
                        size="small"
                        icon={<PlugConnectedCheckmark20Regular />}
                        onClick={() => onTest(peer)}
                        disabled={testMutation.isPending}
                      >
                        Test
                      </Button>
                      {canManagePeers ? (
                        <>
                          <Button
                            appearance="outline"
                            size="small"
                            icon={<Edit20Regular />}
                            onClick={() =>
                              setDialog({ open: true, mode: "edit", peer })
                            }
                          >
                            Edit
                          </Button>
                          <Button
                            appearance="subtle"
                            icon={<Delete20Regular className="text-destructive" />}
                            onClick={() => onDelete(peer)}
                            disabled={deleteMutation.isPending}
                            aria-label="Delete peer"
                          />
                        </>
                      ) : null}
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
