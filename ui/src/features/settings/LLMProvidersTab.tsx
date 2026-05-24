import { useEffect, useState } from "react";
import { Badge, Button, Input } from "@fluentui/react-components";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useSettingsSection,
  useUpdateSettingsSection,
  useTestLLMProvider,
  type ConnectionTestResult,
} from "@/api/queries";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

interface ProviderConfig {
  api_key?: string;
  api_base?: string;
  api_version?: string;
}

type ProvidersData = Record<string, ProviderConfig>;

interface ProviderDef {
  id: string;
  label: string;
  description: string;
  fields: Array<{ name: keyof ProviderConfig; label: string; placeholder: string; secret?: boolean }>;
}

const PROVIDERS: ProviderDef[] = [
  {
    id: "openai",
    label: "OpenAI",
    description: "GPT-4, GPT-4o, o-series. Reads OPENAI_API_KEY at runtime.",
    fields: [
      { name: "api_key", label: "API key", placeholder: "sk-…", secret: true },
      { name: "api_base", label: "API base (optional)", placeholder: "https://api.openai.com/v1" },
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    description: "Claude (Opus, Sonnet, Haiku). Reads ANTHROPIC_API_KEY.",
    fields: [{ name: "api_key", label: "API key", placeholder: "sk-ant-…", secret: true }],
  },
  {
    id: "azure",
    label: "Azure OpenAI",
    description: "Azure-hosted OpenAI deployments. Maps to AZURE_API_KEY / AZURE_API_BASE / AZURE_API_VERSION.",
    fields: [
      { name: "api_key", label: "API key", placeholder: "Azure key", secret: true },
      { name: "api_base", label: "Endpoint", placeholder: "https://my-resource.openai.azure.com/" },
      { name: "api_version", label: "API version", placeholder: "2024-12-01-preview" },
    ],
  },
  {
    id: "google",
    label: "Google Gemini",
    description: "Gemini 2.5 Flash / Pro via the Gemini API. Reads GEMINI_API_KEY.",
    fields: [{ name: "api_key", label: "API key", placeholder: "Gemini key", secret: true }],
  },
  {
    id: "ollama",
    label: "Ollama (local)",
    description: "Local OpenAI-compatible server. Only the api_base is needed.",
    fields: [
      { name: "api_base", label: "API base", placeholder: "http://localhost:11434" },
    ],
  },
];

function maskedPlaceholder(secret: string | undefined): string {
  if (!secret) return "";
  if (secret.length <= 8) return "••••";
  return `${secret.slice(0, 4)}…${secret.slice(-4)}`;
}

export default function LLMProvidersTab() {
  const sectionQuery = useSettingsSection<ProvidersData>("llm_providers");
  const update = useUpdateSettingsSection<ProvidersData>();
  const probe = useTestLLMProvider();

  const stored: ProvidersData = sectionQuery.data?.data ?? {};
  const [drafts, setDrafts] = useState<ProvidersData>({});
  const [probeResults, setProbeResults] = useState<Record<string, ConnectionTestResult>>({});

  useEffect(() => {
    setDrafts({});
  }, [sectionQuery.data]);

  if (isForbiddenError(sectionQuery.error)) {
    return <ForbiddenNotice error={sectionQuery.error} area="LLM provider settings" />;
  }

  const setField = (provider: string, field: keyof ProviderConfig, value: string) => {
    setDrafts((prev) => ({
      ...prev,
      [provider]: { ...(prev[provider] ?? stored[provider] ?? {}), [field]: value },
    }));
  };

  const saveProvider = (provider: string) => {
    const merged: ProvidersData = { ...stored };
    const next = drafts[provider];
    if (next) {
      merged[provider] = { ...(merged[provider] ?? {}), ...next };
    }
    update.mutate(
      { section: "llm_providers", data: merged },
      {
        onSuccess: () => {
          setDrafts((prev) => {
            const { [provider]: _omit, ...rest } = prev;
            return rest;
          });
        },
      },
    );
  };

  const testProvider = async (provider: string) => {
    setProbeResults((prev) => ({ ...prev, [provider]: { ok: false, detail: "Probing…" } }));
    try {
      const result = await probe.mutateAsync(provider);
      setProbeResults((prev) => ({ ...prev, [provider]: result }));
    } catch (err) {
      setProbeResults((prev) => ({
        ...prev,
        [provider]: { ok: false, detail: err instanceof Error ? err.message : "Unknown error" },
      }));
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>LLM Providers</CardTitle>
          <CardDescription>
            Provide API credentials for the providers you use. Keys are stored encrypted on the
            server (Fernet) and applied to the runtime immediately — no restart required.
          </CardDescription>
        </CardHeader>
      </Card>

      {PROVIDERS.map((p) => {
        const current: ProviderConfig = { ...(stored[p.id] ?? {}), ...(drafts[p.id] ?? {}) };
        const dirty = Boolean(drafts[p.id]);
        const test = probeResults[p.id];
        return (
          <Card key={p.id}>
            <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
              <div>
                <CardTitle className="text-base">{p.label}</CardTitle>
                <CardDescription>{p.description}</CardDescription>
              </div>
              {Object.keys(stored[p.id] ?? {}).length > 0 ? (
                <Badge color="success">Configured</Badge>
              ) : (
                <Badge appearance="tint" color="subtle">Not configured</Badge>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {p.fields.map((field) => (
                <div key={field.name} className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor={`${p.id}-${field.name}`}>
                    {field.label}
                  </label>
                  <Input
                    id={`${p.id}-${field.name}`}
                    type={field.secret ? "password" : "text"}
                    autoComplete="off"
                    placeholder={
                      field.secret
                        ? stored[p.id]?.[field.name]
                          ? maskedPlaceholder(stored[p.id]?.[field.name])
                          : field.placeholder
                        : field.placeholder
                    }
                    value={current[field.name] ?? ""}
                    onChange={(_, data) => setField(p.id, field.name, data.value)}
                  />
                </div>
              ))}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button
                  appearance="primary"
                  onClick={() => saveProvider(p.id)}
                  disabled={!dirty || update.isPending}
                >
                  {update.isPending ? "Saving…" : "Save"}
                </Button>
                <Button
                  appearance="outline"
                  onClick={() => testProvider(p.id)}
                  disabled={probe.isPending}
                >
                  Test connection
                </Button>
                {test ? (
                  <span
                    className={
                      test.ok ? "text-xs text-success" : "text-xs text-destructive"
                    }
                  >
                    {test.detail}
                  </span>
                ) : null}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
