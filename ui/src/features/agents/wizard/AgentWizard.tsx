import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import yaml from "js-yaml";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  Save,
  Settings2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  EMPTY_PROFILE_FORM,
  formToProfileConfig,
  type ProfileFormValues,
} from "@/features/agents/schema";
import { useCreateProfile } from "@/api/queries";
import { ApiError } from "@/api/client";
import {
  EMPTY_WIZARD_STATE,
  deriveProfileId,
  type WizardState,
} from "@/features/agents/wizard/types";
import { Step1Template } from "@/features/agents/wizard/steps/Step1Template";
import { Step2Identity } from "@/features/agents/wizard/steps/Step2Identity";
import { Step3Capabilities } from "@/features/agents/wizard/steps/Step3Capabilities";
import { Step4Personality } from "@/features/agents/wizard/steps/Step4Personality";
import { Step5Test } from "@/features/agents/wizard/steps/Step5Test";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: 1, label: "Vorlage" },
  { id: 2, label: "Vorstellen" },
  { id: 3, label: "Fähigkeiten" },
  { id: 4, label: "Persönlichkeit" },
  { id: 5, label: "Testen" },
] as const;

type StepNumber = (typeof STEPS)[number]["id"];

function wizardToProfileForm(state: WizardState): ProfileFormValues {
  return {
    ...EMPTY_PROFILE_FORM,
    name: state.name || deriveProfileId(state.displayName),
    display_name: state.displayName,
    description: state.description,
    system_prompt: state.systemPrompt,
    tools: state.tools,
  };
}

export function AgentWizard() {
  const navigate = useNavigate();
  const createMutation = useCreateProfile();
  const [step, setStep] = useState<StepNumber>(1);
  const [state, setState] = useState<WizardState>(EMPTY_WIZARD_STATE);
  const [error, setError] = useState<string | null>(null);

  function update(patch: Partial<WizardState>) {
    setState((prev) => ({ ...prev, ...patch }));
  }

  function selectTemplate(template: WizardState["template"]) {
    if (!template) return;
    setState((prev) => ({
      ...prev,
      template,
      emoji: template.emoji || prev.emoji,
      tools: Array.from(new Set([...prev.tools, ...template.recommended_tools])),
      skills: Array.from(new Set([...prev.skills, ...template.recommended_skills])),
      tone: template.tone_default || prev.tone,
      language: template.language_default || prev.language,
      // Reset the system prompt so step 4's compose picks up the new template.
      systemPrompt: "",
      promptUsedAI: false,
    }));
  }

  // When the user enters step 4 with no prompt yet, kick off a deterministic
  // compose so the textarea isn't empty. Users can tweak or hit "Mit KI verfeinern".
  useEffect(() => {
    if (step === 4 && !state.systemPrompt && state.template) {
      // Build a deterministic prompt locally so we don't depend on the LLM here.
      const lines: string[] = [];
      const body = state.template.system_prompt_template.trim();
      if (body) lines.push(body);
      if (state.description.trim()) {
        lines.push(`Was du für den Nutzer tust:\n${state.description.trim()}`);
      }
      const styleLines: string[] = [];
      if (state.tone) styleLines.push(`Tonfall: ${state.tone}`);
      if (state.language) styleLines.push(`Antworte standardmäßig auf: ${state.language}`);
      if (styleLines.length > 0) {
        lines.push(
          "Stil:\n" + styleLines.map((line) => `- ${line}`).join("\n"),
        );
      }
      setState((prev) => ({
        ...prev,
        systemPrompt: lines.join("\n\n").trim() + "\n",
      }));
    }
  }, [step, state.template, state.description, state.tone, state.language, state.systemPrompt]);

  const canAdvance = useMemo(() => {
    switch (step) {
      case 1:
        return state.template !== null;
      case 2:
        return state.displayName.trim().length > 0 && state.name.trim().length > 0;
      case 3:
        return true; // tools optional
      case 4:
        return state.systemPrompt.trim().length > 0;
      case 5:
        return true;
      default:
        return false;
    }
  }, [step, state]);

  async function handleCreate(openInChat: boolean) {
    setError(null);
    const profileForm = wizardToProfileForm(state);
    const config = formToProfileConfig(profileForm);
    try {
      const created = await createMutation.mutateAsync({
        name: profileForm.name,
        config,
      });
      if (openInChat) {
        navigate(`/chat?profile=${encodeURIComponent(created.name)}`);
      } else {
        navigate(`/agents/${encodeURIComponent(created.name)}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/agents">
            <ChevronLeft className="mr-1 h-4 w-4" />
            Zurück zur Liste
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to="/agents/new?advanced=1">
            <Settings2 className="mr-2 h-4 w-4" />
            Direkt in den Profi-Editor
          </Link>
        </Button>
      </div>

      <Card className="p-6">
        <ol className="mb-6 flex flex-wrap items-center gap-2">
          {STEPS.map((s, idx) => {
            const isActive = step === s.id;
            const isDone = step > s.id;
            return (
              <li key={s.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    // Allow jumping back to earlier steps freely.
                    if (s.id <= step) setStep(s.id);
                  }}
                  className={cn(
                    "flex items-center gap-2 rounded-full px-3 py-1 text-sm transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : isDone
                        ? "bg-primary/10 text-primary hover:bg-primary/20"
                        : "bg-muted text-muted-foreground",
                  )}
                  disabled={s.id > step}
                >
                  <span
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
                      isActive
                        ? "bg-primary-foreground/20"
                        : isDone
                          ? "bg-primary text-primary-foreground"
                          : "bg-background",
                    )}
                  >
                    {isDone ? <Check className="h-3 w-3" /> : s.id}
                  </span>
                  {s.label}
                </button>
                {idx < STEPS.length - 1 ? (
                  <span className="text-muted-foreground">›</span>
                ) : null}
              </li>
            );
          })}
        </ol>

        <div className="min-h-[400px]">
          {step === 1 ? (
            <Step1Template
              selectedId={state.template?.id ?? null}
              onSelect={selectTemplate}
            />
          ) : step === 2 ? (
            <Step2Identity state={state} onChange={update} />
          ) : step === 3 ? (
            <Step3Capabilities state={state} onChange={update} />
          ) : step === 4 ? (
            <Step4Personality state={state} onChange={update} />
          ) : (
            <Step5Test state={state} />
          )}
        </div>

        {error ? (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => setStep((s) => (s > 1 ? ((s - 1) as StepNumber) : s))}
            disabled={step === 1}
          >
            <ArrowLeft className="mr-2 h-4 w-4" /> Zurück
          </Button>

          {step < 5 ? (
            <Button
              type="button"
              onClick={() =>
                setStep((s) => (s < 5 ? ((s + 1) as StepNumber) : s))
              }
              disabled={!canAdvance}
            >
              Weiter <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => handleCreate(false)}
                disabled={createMutation.isPending}
              >
                <Save className="mr-2 h-4 w-4" /> Anlegen &amp; schließen
              </Button>
              <Button
                type="button"
                onClick={() => handleCreate(true)}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? "Lege an…" : "Anlegen & im Chat öffnen"}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Tiny YAML preview for power users — collapsed by default. */}
      <details className="rounded-md border border-border bg-muted/20 p-3 text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          Vorschau: YAML-Konfiguration anzeigen
        </summary>
        <pre className="mt-2 overflow-auto scrollbar-thin font-mono text-[11px] leading-relaxed">
          {(() => {
            try {
              const profileForm = wizardToProfileForm(state);
              return yaml.dump(formToProfileConfig(profileForm), {
                noRefs: true,
                sortKeys: false,
              });
            } catch (err) {
              return `# YAML-Fehler: ${(err as Error).message}`;
            }
          })()}
        </pre>
      </details>
    </div>
  );
}
