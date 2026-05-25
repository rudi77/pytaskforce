import { useState } from "react";
import { Badge, Button, Field, Input } from "@fluentui/react-components";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useChannelBots,
  useCreateChannelBot,
  useUpdateChannelBot,
  useDeleteChannelBot,
  useTestChannelBot,
  useBotPollerStatus,
  type BotConfig,
  type BotOwnerKind,
  type PairingMode,
  type ConnectionTestResult,
} from "@/api/queries";
import { useCurrentPermissions } from "@/lib/permissions";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

const CHANNEL_TYPES = [
  { id: "telegram", label: "Telegram" },
  { id: "teams", label: "Microsoft Teams" },
];

const PAIRING_HINTS: Record<PairingMode, string> = {
  implicit: "Bot belongs to one user — every message routes to that user, no /link needed.",
  paired: "Each chat must run /link <code> once to claim its user.",
  anonymous: "No per-user routing — all messages handled by default_agent without user context.",
};

interface BotDraft {
  id: string;
  channel_type: string;
  bot_token: string;
  owner_kind: BotOwnerKind;
  owner_user_id: string | null;
  default_agent: string;
  pairing_mode: PairingMode | "";
  enabled: boolean;
}

function emptyDraft(currentUserId: string | null): BotDraft {
  return {
    id: "",
    channel_type: "telegram",
    bot_token: "",
    owner_kind: "user",
    owner_user_id: currentUserId,
    default_agent: "",
    pairing_mode: "",
    enabled: true,
  };
}

function draftToConfig(draft: BotDraft): BotConfig {
  return {
    id: draft.id.trim(),
    channel_type: draft.channel_type,
    bot_token: draft.bot_token,
    owner_kind: draft.owner_kind,
    owner_user_id: draft.owner_kind === "user" ? draft.owner_user_id : null,
    default_agent: draft.default_agent.trim() || null,
    pairing_mode: (draft.pairing_mode || null) as PairingMode | null,
    enabled: draft.enabled,
  };
}

function configToDraft(bot: BotConfig): BotDraft {
  return {
    id: bot.id,
    channel_type: bot.channel_type,
    bot_token: bot.bot_token ?? "",
    owner_kind: bot.owner_kind,
    owner_user_id: bot.owner_user_id,
    default_agent: bot.default_agent ?? "",
    pairing_mode: bot.pairing_mode ?? "",
    enabled: bot.enabled,
  };
}

function BotRow({
  bot,
  currentUserId,
  canManage,
  running,
  onEdit,
  onDelete,
  onTest,
}: {
  bot: BotConfig;
  currentUserId: string | null;
  canManage: boolean;
  running: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onTest: (recipient: string) => Promise<ConnectionTestResult>;
}) {
  const [recipient, setRecipient] = useState("");
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  const isOwn = bot.owner_kind === "user" && bot.owner_user_id === currentUserId;
  const ownerBadge =
    bot.owner_kind === "tenant" ? (
      <Badge color="brand">Tenant-shared</Badge>
    ) : isOwn ? (
      <Badge color="success">Mine</Badge>
    ) : (
      <Badge appearance="tint" color="subtle">User: {bot.owner_user_id?.slice(0, 8)}…</Badge>
    );

  const handleTest = async () => {
    if (!recipient) return;
    setTesting(true);
    setResult(null);
    try {
      setResult(await onTest(recipient));
    } catch (err) {
      setResult({
        ok: false,
        detail: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base">{bot.id}</CardTitle>
            {ownerBadge}
            <Badge appearance="outline" color="subtle">{bot.channel_type}</Badge>
            {bot.pairing_mode ? (
              <Badge appearance="tint" color="subtle">pairing: {bot.pairing_mode}</Badge>
            ) : null}
            {!bot.enabled ? (
              <Badge color="warning">disabled</Badge>
            ) : running ? (
              <Badge color="success">running</Badge>
            ) : (
              <Badge color="warning">not running</Badge>
            )}
          </div>
          <CardDescription>
            {bot.default_agent ? `Default agent: ${bot.default_agent}` : "Default agent: tenant default"}
            {bot.pairing_mode ? ` · ${PAIRING_HINTS[bot.pairing_mode]}` : ""}
          </CardDescription>
          <div className="text-xs text-muted-foreground">
            Token: <code>{bot.bot_token || "—"}</code>
          </div>
        </div>
        <div className="flex gap-2">
          {canManage ? (
            <>
              <Button appearance="outline" size="small" onClick={onEdit}>
                Edit
              </Button>
              <Button appearance="outline" size="small" onClick={onDelete}>
                Delete
              </Button>
            </>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 border-t pt-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={recipient}
            onChange={(_, data) => setRecipient(data.value)}
            placeholder="recipient id (e.g. Telegram chat_id)"
            className="max-w-xs"
          />
          <Button
            appearance="outline"
            onClick={handleTest}
            disabled={testing || !recipient}
          >
            {testing ? "Sending…" : "Send test"}
          </Button>
          {result ? (
            <span className={result.ok ? "text-xs text-success" : "text-xs text-destructive"}>
              {result.detail}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function BotForm({
  draft,
  setDraft,
  onSave,
  onCancel,
  saving,
  isEdit,
  isAdmin,
  currentUserId,
}: {
  draft: BotDraft;
  setDraft: (d: BotDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  isEdit: boolean;
  isAdmin: boolean;
  currentUserId: string | null;
}) {
  return (
    <Card className="border-primary">
      <CardHeader>
        <CardTitle className="text-base">{isEdit ? `Edit bot: ${draft.id}` : "Add bot"}</CardTitle>
        <CardDescription>
          Personal bots are private to you. Tenant-shared bots require admin
          permission and are visible to everyone in the tenant.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Field label={{ children: "Bot id (slug)", htmlFor: "bot-id" }}>
          <Input
            id="bot-id"
            value={draft.id}
            onChange={(_, data) => setDraft({ ...draft, id: data.value })}
            placeholder="rudi-butler"
            disabled={isEdit}
            autoComplete="off"
          />
        </Field>

        <Field
          label={{ children: "Channel type", htmlFor: "bot-channel-type" }}
        >
          {/* Raw <select> kept — Fluent Dropdown has a different
           *  controlled-state API (selectedOptions array + onOptionSelect)
           *  that's a separate primitive migration. */}
          <select
            id="bot-channel-type"
            value={draft.channel_type}
            onChange={(e) => setDraft({ ...draft, channel_type: e.target.value })}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            {CHANNEL_TYPES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label={{ children: "Bot token", htmlFor: "bot-token" }}>
          <Input
            id="bot-token"
            type="password"
            value={draft.bot_token}
            onChange={(_, data) => setDraft({ ...draft, bot_token: data.value })}
            placeholder="123456:ABC-…"
            autoComplete="off"
          />
        </Field>

        <div className="space-y-1.5">
          <label className="text-sm font-medium">Owner</label>
          <div className="flex gap-3">
            {/* Raw radios kept — Fluent Radio/RadioGroup is its own
             *  primitive sweep. */}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={draft.owner_kind === "user"}
                onChange={() =>
                  setDraft({ ...draft, owner_kind: "user", owner_user_id: currentUserId })
                }
              />
              Just me (personal bot)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={draft.owner_kind === "tenant"}
                disabled={!isAdmin}
                onChange={() => setDraft({ ...draft, owner_kind: "tenant", owner_user_id: null })}
              />
              Tenant-shared
              {!isAdmin ? (
                <span className="text-xs text-muted-foreground">(admin only)</span>
              ) : null}
            </label>
          </div>
        </div>

        <Field
          label={{
            children: "Default agent (optional)",
            htmlFor: "bot-default-agent",
          }}
          hint="Which agent answers messages on this bot. Empty = tenant default."
        >
          <Input
            id="bot-default-agent"
            value={draft.default_agent}
            onChange={(_, data) => setDraft({ ...draft, default_agent: data.value })}
            placeholder="butler"
            autoComplete="off"
          />
        </Field>

        <Field
          label={{ children: "Pairing mode", htmlFor: "bot-pairing-mode" }}
          hint={draft.pairing_mode ? PAIRING_HINTS[draft.pairing_mode] : undefined}
        >
          <select
            id="bot-pairing-mode"
            value={draft.pairing_mode}
            onChange={(e) =>
              setDraft({ ...draft, pairing_mode: e.target.value as PairingMode | "" })
            }
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            <option value="">
              auto (
              {draft.owner_kind === "user" ? "implicit" : "paired"})
            </option>
            <option value="implicit">implicit — owner only, no /link</option>
            <option value="paired">paired — /link required</option>
            <option value="anonymous">anonymous — no per-user routing</option>
          </select>
        </Field>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          Enabled
        </label>

        <div className="flex items-center gap-2 border-t pt-3">
          <Button
            appearance="primary"
            onClick={onSave}
            disabled={saving || !draft.id || !draft.bot_token}
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Add bot"}
          </Button>
          <Button appearance="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ChannelsTab() {
  const botsQuery = useChannelBots();
  const pollerStatus = useBotPollerStatus();
  const permissions = useCurrentPermissions();
  const createBot = useCreateChannelBot();
  const updateBot = useUpdateChannelBot();
  const deleteBot = useDeleteChannelBot();
  const testBot = useTestChannelBot();

  const currentUserId = permissions.data?.userId ?? null;
  const isAdmin = permissions.can("tenant:manage");

  const [draft, setDraft] = useState<BotDraft | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  if (isForbiddenError(botsQuery.error)) {
    return <ForbiddenNotice error={botsQuery.error} area="channel bot settings" />;
  }

  if (botsQuery.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  const bots = botsQuery.data?.bots ?? [];
  const runningSet = new Set(pollerStatus.data?.running_bot_ids ?? []);
  const myBots = bots.filter((b) => b.owner_kind === "user" && b.owner_user_id === currentUserId);
  const sharedBots = bots.filter((b) => b.owner_kind === "tenant");
  const otherUserBots = bots.filter(
    (b) => b.owner_kind === "user" && b.owner_user_id !== currentUserId,
  );

  const startAdd = (ownerKind: BotOwnerKind) =>
    setDraft({ ...emptyDraft(currentUserId), owner_kind: ownerKind, owner_user_id: ownerKind === "user" ? currentUserId : null });

  const startEdit = (bot: BotConfig) => {
    setEditingId(bot.id);
    setDraft(configToDraft(bot));
  };

  const handleSave = async () => {
    if (!draft) return;
    const config = draftToConfig(draft);
    try {
      if (editingId) {
        await updateBot.mutateAsync(config);
      } else {
        await createBot.mutateAsync(config);
      }
      setDraft(null);
      setEditingId(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      alert(msg);
    }
  };

  const handleDelete = async (botId: string) => {
    if (!confirm(`Delete bot "${botId}"? This cannot be undone.`)) return;
    try {
      await deleteBot.mutateAsync(botId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      alert(msg);
    }
  };

  const handleTest = (botId: string) => async (recipient: string) =>
    testBot.mutateAsync({ botId, recipient });

  const saving = createBot.isPending || updateBot.isPending;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Communication Channels</CardTitle>
          <CardDescription>
            Configure bots for Telegram and (later) Teams. Personal bots only deliver
            messages to you. Tenant-shared bots can be used by every user in the tenant via
            the <code>/link</code> pairing flow. Add, edit, or remove bots without restarting
            — the backend reconciles polling loops on save (badge below shows the live state).
          </CardDescription>
        </CardHeader>
      </Card>

      {draft ? (
        <BotForm
          draft={draft}
          setDraft={setDraft}
          onSave={handleSave}
          onCancel={() => {
            setDraft(null);
            setEditingId(null);
          }}
          saving={saving}
          isEdit={editingId !== null}
          isAdmin={isAdmin}
          currentUserId={currentUserId}
        />
      ) : null}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base">My personal bots</CardTitle>
            <CardDescription>Only delivered to your user account.</CardDescription>
          </div>
          {!draft ? (
            <Button appearance="primary" onClick={() => startAdd("user")}>
              Add personal bot
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-3">
          {myBots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No personal bots yet.</p>
          ) : (
            myBots.map((bot) => (
              <BotRow
                key={bot.id}
                bot={bot}
                currentUserId={currentUserId}
                canManage
                running={runningSet.has(bot.id)}
                onEdit={() => startEdit(bot)}
                onDelete={() => handleDelete(bot.id)}
                onTest={handleTest(bot.id)}
              />
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base">Tenant-shared bots</CardTitle>
            <CardDescription>
              Visible to every user in the tenant. Editable only by admins.
            </CardDescription>
          </div>
          {!draft && isAdmin ? (
            <Button appearance="primary" onClick={() => startAdd("tenant")}>
              Add shared bot
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-3">
          {sharedBots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tenant-shared bots yet.</p>
          ) : (
            sharedBots.map((bot) => (
              <BotRow
                key={bot.id}
                bot={bot}
                currentUserId={currentUserId}
                canManage={isAdmin}
                running={runningSet.has(bot.id)}
                onEdit={() => startEdit(bot)}
                onDelete={() => handleDelete(bot.id)}
                onTest={handleTest(bot.id)}
              />
            ))
          )}
        </CardContent>
      </Card>

      {isAdmin && otherUserBots.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Other users' personal bots</CardTitle>
            <CardDescription>
              Visible to admins for inventory; tokens are masked. Use these to revoke when
              a user can no longer manage their bot themselves.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {otherUserBots.map((bot) => (
              <BotRow
                key={bot.id}
                bot={bot}
                currentUserId={currentUserId}
                canManage={isAdmin}
                running={runningSet.has(bot.id)}
                onEdit={() => startEdit(bot)}
                onDelete={() => handleDelete(bot.id)}
                onTest={handleTest(bot.id)}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
