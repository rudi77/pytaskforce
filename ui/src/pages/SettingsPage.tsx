import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTheme } from "@/app/theme-provider";
import { useSettings } from "@/lib/settings";
import LLMProvidersTab from "@/features/settings/LLMProvidersTab";
import ChannelsTab from "@/features/settings/ChannelsTab";
import AgentVisibilityTab from "@/features/settings/AgentVisibilityTab";
import ApprovalsTab from "@/features/settings/ApprovalsTab";
import IntegrationsTab from "@/features/settings/IntegrationsTab";

function GeneralTab() {
  const { preference, setPreference } = useTheme();
  const apiBaseUrl = useSettings((s) => s.apiBaseUrl);
  const apiToken = useSettings((s) => s.apiToken);
  const setApiBaseUrl = useSettings((s) => s.setApiBaseUrl);
  const setApiToken = useSettings((s) => s.setApiToken);

  const [draftUrl, setDraftUrl] = useState(apiBaseUrl);
  const [draftToken, setDraftToken] = useState(apiToken);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setApiBaseUrl(draftUrl);
    setApiToken(draftToken);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Choose between light, dark, or follow system preference.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {(["light", "dark", "system"] as const).map((option) => (
            <Button
              key={option}
              variant={preference === option ? "default" : "outline"}
              size="sm"
              onClick={() => setPreference(option)}
            >
              {option[0].toUpperCase() + option.slice(1)}
            </Button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API connection</CardTitle>
          <CardDescription>
            Base URL of the Taskforce API. Leave empty to use the dev-server proxy
            (forwards <code>/api/v1</code> and <code>/health</code> to the configured backend).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="api-base-url">
              API base URL
            </label>
            <Input
              id="api-base-url"
              value={draftUrl}
              onChange={(e) => setDraftUrl(e.target.value)}
              placeholder="http://localhost:8070"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="api-token">
              API token (optional)
            </label>
            <Input
              id="api-token"
              type="password"
              value={draftToken}
              onChange={(e) => setDraftToken(e.target.value)}
              placeholder="Bearer token, sent as Authorization header"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Fallback for headless / CI use. Interactive users sign in via{" "}
              <code>/login</code> instead.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleSave}>Save</Button>
            {saved ? <span className="text-xs text-success">Saved.</span> : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

const TABS: Array<{ value: string; label: string; render: () => JSX.Element }> = [
  { value: "general", label: "General", render: () => <GeneralTab /> },
  { value: "llm", label: "LLM Providers", render: () => <LLMProvidersTab /> },
  { value: "channels", label: "Channels", render: () => <ChannelsTab /> },
  { value: "agents", label: "Agents", render: () => <AgentVisibilityTab /> },
  { value: "approvals", label: "Approvals", render: () => <ApprovalsTab /> },
  { value: "integrations", label: "Integrations", render: () => <IntegrationsTab /> },
];

export default function SettingsPage() {
  return (
    <Tabs defaultValue="general" className="space-y-4">
      <TabsList className="h-auto flex-wrap">
        {TABS.map((t) => (
          <TabsTrigger key={t.value} value={t.value}>
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {TABS.map((t) => (
        <TabsContent key={t.value} value={t.value}>
          {t.render()}
        </TabsContent>
      ))}
    </Tabs>
  );
}
