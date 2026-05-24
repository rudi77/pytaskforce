import { useState } from "react";
import { Button, Input, Tab, TabList } from "@fluentui/react-components";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
              appearance={preference === option ? "primary" : "outline"}
              size="small"
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
              onChange={(_, data) => setDraftUrl(data.value)}
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
              onChange={(_, data) => setDraftToken(data.value)}
              placeholder="Bearer token, sent as Authorization header"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Fallback for headless / CI use. Interactive users sign in via{" "}
              <code>/login</code> instead.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button appearance="primary" onClick={handleSave}>Save</Button>
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
  // Fluent TabList is controlled (selectedValue + onTabSelect) whereas Radix
  // Tabs was uncontrolled with defaultValue. State lives here now.
  const [selected, setSelected] = useState<string>("general");
  const active = TABS.find((t) => t.value === selected) ?? TABS[0];

  return (
    <div className="space-y-4">
      <TabList
        selectedValue={selected}
        onTabSelect={(_, data) => setSelected(String(data.value))}
      >
        {TABS.map((t) => (
          <Tab key={t.value} value={t.value}>
            {t.label}
          </Tab>
        ))}
      </TabList>
      <div>{active.render()}</div>
    </div>
  );
}
