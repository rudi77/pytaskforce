import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { deriveProfileId, type WizardState } from "@/features/agents/wizard/types";

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

const EMOJI_OPTIONS = ["✨", "🤖", "🧾", "🛠️", "🔎", "🤝", "📊", "📝", "💡", "🎯"];

export function Step2Identity({ state, onChange }: Props) {
  const handleNameChange = (value: string) => {
    const next: Partial<WizardState> = { displayName: value };
    // Only auto-derive the slug while the user hasn't typed a custom one.
    if (!state.name || state.name === deriveProfileId(state.displayName)) {
      next.name = deriveProfileId(value);
    }
    onChange(next);
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <p className="text-sm text-muted-foreground">
        Gib deinem Agenten einen Namen und beschreibe in eigenen Worten, wofür er
        da ist. Das hilft uns, später den richtigen Tonfall zu treffen.
      </p>

      <div className="space-y-2">
        <Label htmlFor="wizard-emoji">Symbol</Label>
        <div className="flex flex-wrap gap-2">
          {EMOJI_OPTIONS.map((emoji) => (
            <button
              key={emoji}
              type="button"
              onClick={() => onChange({ emoji })}
              className={
                "rounded-md border px-3 py-2 text-2xl leading-none transition-colors " +
                (emoji === state.emoji
                  ? "border-primary bg-primary/10"
                  : "border-border hover:bg-accent")
              }
              aria-label={`Symbol ${emoji}`}
            >
              {emoji}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="wizard-displayname">Wie soll dein Agent heißen?</Label>
        <Input
          id="wizard-displayname"
          value={state.displayName}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="z.B. Anna, Max, Buchhaltungs-Assistent…"
          autoFocus
        />
        {state.displayName ? (
          <p className="text-xs text-muted-foreground">
            Interner Name (wird automatisch erzeugt):{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
              {state.name || deriveProfileId(state.displayName)}
            </code>
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="wizard-description">Was soll er für dich tun?</Label>
        <Textarea
          id="wizard-description"
          value={state.description}
          onChange={(e) => onChange({ description: e.target.value })}
          placeholder={
            state.template?.persona_hint ??
            "Beschreibe in 1-2 Sätzen, wobei dir dieser Agent helfen soll."
          }
          rows={4}
        />
      </div>
    </div>
  );
}
