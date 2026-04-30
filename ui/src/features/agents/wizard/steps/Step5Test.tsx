import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { labelForTool } from "@/features/capabilities/capability-groups";
import type { WizardState } from "@/features/agents/wizard/types";

interface Props {
  state: WizardState;
}

export function Step5Test({ state }: Props) {
  const promptPreview =
    state.systemPrompt.length > 280
      ? state.systemPrompt.slice(0, 280).trimEnd() + "…"
      : state.systemPrompt;

  return (
    <div className="space-y-5 max-w-3xl">
      <p className="text-sm text-muted-foreground">
        Letzter Check, bevor wir deinen Agenten anlegen. Wenn alles passt, klick
        auf <strong>Anlegen &amp; im Chat öffnen</strong> — dort kannst du den
        Agenten direkt mit einem der Beispiele unten ausprobieren.
      </p>

      <Card>
        <CardContent className="space-y-2 p-5">
          <div className="flex items-center gap-3">
            <span className="text-3xl leading-none">{state.emoji}</span>
            <div>
              <p className="text-base font-semibold">{state.displayName}</p>
              <p className="font-mono text-xs text-muted-foreground">
                {state.name}
              </p>
            </div>
          </div>
          {state.description ? (
            <p className="text-sm text-muted-foreground">{state.description}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Ausgewählte Werkzeuge ({state.tools.length})
          </p>
          {state.tools.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {state.tools.map((tool) => (
                <Badge key={tool} variant="outline">
                  {labelForTool(tool)}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Noch keine Werkzeuge ausgewählt — der Agent kann nur antworten,
              aber nichts „tun“. Geh zurück zu Schritt 3, wenn du das ändern willst.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Stil &amp; Verhalten
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="secondary">Tonfall: {state.tone}</Badge>
            <Badge variant="secondary">Sprache: {state.language}</Badge>
            {state.promptUsedAI ? (
              <Badge variant="default">Prompt mit KI verfeinert</Badge>
            ) : null}
          </div>
          {promptPreview ? (
            <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed scrollbar-thin">
              {promptPreview}
            </pre>
          ) : (
            <p className="text-sm text-amber-600">
              Achtung: Du hast noch keinen System-Prompt erzeugt. Geh zurück zu
              Schritt 4 und klicke auf „Prompt erzeugen“.
            </p>
          )}
        </CardContent>
      </Card>

      {state.template && state.template.example_prompts.length > 0 ? (
        <Card>
          <CardContent className="space-y-2 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Probier es im Chat
            </p>
            <ul className="space-y-1">
              {state.template.example_prompts.map((example) => (
                <li
                  key={example}
                  className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-sm"
                >
                  {example}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Diese Beispiele zeigen, wofür dieser Agent gemacht ist. Im Chat
              kannst du sie kopieren oder eigene Fragen stellen.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
