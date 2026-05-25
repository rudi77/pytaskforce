import { useState } from "react";
import {
  Warning20Regular,
  Sparkle20Regular,
  Wand20Regular,
  Wand16Regular,
} from "@fluentui/react-icons";
import { Field } from "@fluentui/react-components";

import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useComposePrompt } from "@/api/queries";
import { ApiError } from "@/api/client";
import {
  LANGUAGE_OPTIONS,
  TONE_OPTIONS,
  type WizardState,
} from "@/features/agents/wizard/types";
import { cn } from "@/lib/utils";

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

export function Step4Personality({ state, onChange }: Props) {
  const compose = useComposePrompt();
  const [busyMode, setBusyMode] = useState<"deterministic" | "ai" | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);
  const [composeError, setComposeError] = useState<string | null>(null);

  async function handleCompose(useAi: boolean) {
    setBusyMode(useAi ? "ai" : "deterministic");
    setComposeError(null);
    setAiNotice(null);
    try {
      const res = await compose.mutateAsync({
        template_id: state.template?.id ?? null,
        description: state.description,
        tone: state.tone,
        language: state.language,
        rules: state.rules,
        use_ai: useAi,
      });
      onChange({
        systemPrompt: res.system_prompt,
        promptUsedAI: res.used_ai,
      });
      // Honest feedback when the AI was attempted but couldn't produce a
      // refined version: the user got the deterministic draft, and we tell
      // them why.
      if (useAi && res.ai_attempted && !res.used_ai) {
        setAiNotice(
          res.ai_error
            ? `Die KI-Verfeinerung war nicht möglich (${res.ai_error}). Du siehst den deterministischen Entwurf — du kannst ihn manuell anpassen.`
            : "Die KI lieferte keine andere Version. Der deterministische Entwurf ist eingefügt.",
        );
      }
    } catch (err) {
      setComposeError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusyMode(null);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-5">
        <div className="space-y-2">
          <Label>Tonfall</Label>
          <div className="flex flex-wrap gap-2">
            {TONE_OPTIONS.map((tone) => (
              <button
                key={tone.id}
                type="button"
                onClick={() => onChange({ tone: tone.id })}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  state.tone === tone.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-accent",
                )}
              >
                {tone.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Sprache</Label>
          <div className="flex flex-wrap gap-2">
            {LANGUAGE_OPTIONS.map((lang) => (
              <button
                key={lang.id}
                type="button"
                onClick={() => onChange({ language: lang.id })}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  state.language === lang.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-accent",
                )}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </div>

        <Field
          label="Wichtige Regeln (optional)"
          hint="Diese Regeln werden dem Agenten als verbindliche Anweisungen mitgegeben."
        >
          <Textarea
            id="wizard-rules"
            value={state.rules}
            onChange={(e) => onChange({ rules: e.target.value })}
            placeholder={
              "Eine Regel pro Zeile, z.B.\n- Beträge immer mit zwei Nachkommastellen\n- Bei Unklarheit nachfragen\n- Niemals Belege erfinden"
            }
            rows={6}
          />
        </Field>

        {composeError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            <Warning20Regular className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Fehler beim Erzeugen: {composeError}</span>
          </div>
        ) : null}

        {aiNotice ? (
          <div
            role="status"
            className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
          >
            <Warning20Regular className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{aiNotice}</span>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="default"
            onClick={() => handleCompose(false)}
            disabled={busyMode !== null}
          >
            <Sparkle20Regular className="mr-2 h-4 w-4" />
            {busyMode === "deterministic"
              ? "Erzeuge Prompt…"
              : state.systemPrompt
                ? "Prompt neu erzeugen"
                : "Prompt erzeugen"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleCompose(true)}
            disabled={busyMode !== null}
          >
            <Wand20Regular className="mr-2 h-4 w-4" />
            {busyMode === "ai" ? "Verfeinere mit KI…" : "Mit KI verfeinern"}
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm">System-Prompt</Label>
            {state.promptUsedAI ? (
              <Badge variant="default" className="gap-1">
                <Wand16Regular className="h-3 w-3" /> Mit KI verfeinert
              </Badge>
            ) : null}
          </div>
          <Textarea
            value={state.systemPrompt}
            onChange={(e) =>
              onChange({ systemPrompt: e.target.value, promptUsedAI: false })
            }
            placeholder="Klick auf „Prompt erzeugen“ — du kannst hier auch direkt schreiben."
            rows={16}
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">
            Das ist die DNA deines Agenten — was er ist, was er tut, wie er
            antwortet. Du kannst frei editieren.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
