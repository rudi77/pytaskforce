import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  useSettingsSection,
  useUpdateSettingsSection,
  useTestChannel,
  type ConnectionTestResult,
} from "@/api/queries";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

interface ChannelConfig {
  enabled?: boolean;
  bot_token?: string;
  app_id?: string;
  app_password?: string;
}

type ChannelsData = Record<string, ChannelConfig>;

interface ChannelDef {
  id: string;
  label: string;
  description: string;
  fields: Array<{
    name: keyof ChannelConfig;
    label: string;
    placeholder: string;
    secret?: boolean;
  }>;
  testHint: string;
}

const CHANNELS: ChannelDef[] = [
  {
    id: "telegram",
    label: "Telegram",
    description: "Long-poll-based bot connector (no public webhook needed).",
    fields: [
      {
        name: "bot_token",
        label: "Bot token",
        placeholder: "123456:ABC-…",
        secret: true,
      },
    ],
    testHint: "Recipient is the chat_id of your bot (DM your bot once to get it).",
  },
  {
    id: "teams",
    label: "Microsoft Teams",
    description: "Bot Framework outbound. Inbound requires the webhook config in Azure.",
    fields: [
      { name: "app_id", label: "App ID", placeholder: "00000000-0000-…" },
      {
        name: "app_password",
        label: "App secret",
        placeholder: "client secret",
        secret: true,
      },
    ],
    testHint: "Recipient is the Teams conversation reference.",
  },
];

export default function ChannelsTab() {
  const sectionQuery = useSettingsSection<ChannelsData>("channels");
  const update = useUpdateSettingsSection<ChannelsData>();
  const probe = useTestChannel();

  const stored: ChannelsData = sectionQuery.data?.data ?? {};
  const [drafts, setDrafts] = useState<ChannelsData>({});
  const [recipients, setRecipients] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, ConnectionTestResult>>({});

  useEffect(() => {
    setDrafts({});
  }, [sectionQuery.data]);

  if (isForbiddenError(sectionQuery.error)) {
    return <ForbiddenNotice error={sectionQuery.error} area="channel settings" />;
  }

  const setField = (channel: string, field: keyof ChannelConfig, value: string | boolean) => {
    setDrafts((prev) => ({
      ...prev,
      [channel]: { ...(prev[channel] ?? stored[channel] ?? {}), [field]: value },
    }));
  };

  const saveChannel = (channel: string) => {
    const merged: ChannelsData = { ...stored };
    const next = drafts[channel];
    if (next) merged[channel] = { ...(merged[channel] ?? {}), ...next };
    update.mutate(
      { section: "channels", data: merged },
      {
        onSuccess: () => {
          setDrafts((prev) => {
            const { [channel]: _omit, ...rest } = prev;
            return rest;
          });
        },
      },
    );
  };

  const testChannel = async (channel: string) => {
    const recipient = recipients[channel];
    if (!recipient) {
      setResults((prev) => ({
        ...prev,
        [channel]: { ok: false, detail: "Recipient is required." },
      }));
      return;
    }
    setResults((prev) => ({ ...prev, [channel]: { ok: false, detail: "Sending…" } }));
    try {
      const result = await probe.mutateAsync({ channel, recipient });
      setResults((prev) => ({ ...prev, [channel]: result }));
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [channel]: { ok: false, detail: err instanceof Error ? err.message : "Unknown error" },
      }));
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Communication Channels</CardTitle>
          <CardDescription>
            Configure how the agent reaches you proactively. Credentials are encrypted at rest;
            the gateway picks up new values on the next request.
          </CardDescription>
        </CardHeader>
      </Card>

      {CHANNELS.map((c) => {
        const current: ChannelConfig = { ...(stored[c.id] ?? {}), ...(drafts[c.id] ?? {}) };
        const dirty = Boolean(drafts[c.id]);
        const result = results[c.id];
        const isEnabled = current.enabled !== false;
        return (
          <Card key={c.id}>
            <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
              <div>
                <CardTitle className="text-base">{c.label}</CardTitle>
                <CardDescription>{c.description}</CardDescription>
              </div>
              {Object.keys(stored[c.id] ?? {}).length > 0 ? (
                <Badge variant={isEnabled ? "success" : "secondary"}>
                  {isEnabled ? "Configured" : "Disabled"}
                </Badge>
              ) : (
                <Badge variant="secondary">Not configured</Badge>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {c.fields.map((field) => (
                <div key={field.name} className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor={`${c.id}-${field.name}`}>
                    {field.label}
                  </label>
                  <Input
                    id={`${c.id}-${field.name}`}
                    type={field.secret ? "password" : "text"}
                    autoComplete="off"
                    placeholder={field.placeholder}
                    value={(current[field.name] as string | undefined) ?? ""}
                    onChange={(e) => setField(c.id, field.name, e.target.value)}
                  />
                </div>
              ))}

              <label className="flex items-center gap-2 pt-1 text-sm">
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={(e) => setField(c.id, "enabled", e.target.checked)}
                />
                Enabled
              </label>

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button onClick={() => saveChannel(c.id)} disabled={!dirty || update.isPending}>
                  {update.isPending ? "Saving…" : "Save"}
                </Button>
              </div>

              <div className="space-y-1.5 border-t pt-3">
                <p className="text-xs text-muted-foreground">{c.testHint}</p>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    value={recipients[c.id] ?? ""}
                    onChange={(e) =>
                      setRecipients((prev) => ({ ...prev, [c.id]: e.target.value }))
                    }
                    placeholder="recipient id"
                    className="max-w-xs"
                  />
                  <Button
                    variant="outline"
                    onClick={() => testChannel(c.id)}
                    disabled={probe.isPending}
                  >
                    Send test
                  </Button>
                  {result ? (
                    <span
                      className={
                        result.ok ? "text-xs text-success" : "text-xs text-destructive"
                      }
                    >
                      {result.detail}
                    </span>
                  ) : null}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
