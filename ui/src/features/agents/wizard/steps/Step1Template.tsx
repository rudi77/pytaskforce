import { useAgentTemplates, type AgentTemplate } from "@/api/queries";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { labelForTool } from "@/features/capabilities/capability-groups";

interface Props {
  selectedId: string | null;
  onSelect: (template: AgentTemplate) => void;
}

export function Step1Template({ selectedId, onSelect }: Props) {
  const { data, isLoading, error } = useAgentTemplates();
  const templates = data?.templates ?? [];

  if (isLoading) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full" />
        ))}
      </div>
    );
  }

  if (error || templates.length === 0) {
    return (
      <EmptyState
        title="Konnte Vorlagen nicht laden"
        description="Probiere es später noch einmal oder starte mit einer leeren Vorlage."
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Wähle eine Vorlage als Startpunkt — wir füllen automatisch die richtigen
        Werkzeuge und einen passenden Prompt vor. Du kannst alles in den nächsten
        Schritten anpassen.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {templates.map((template) => {
          const isSelected = template.id === selectedId;
          return (
            <button
              key={template.id}
              type="button"
              onClick={() => onSelect(template)}
              className="text-left"
            >
              <Card
                className={cn(
                  "h-full transition-all",
                  isSelected
                    ? "border-primary ring-2 ring-primary/30"
                    : "hover:border-primary/50",
                )}
              >
                <CardContent className="space-y-3 p-5">
                  <div className="flex items-start gap-3">
                    <span className="text-3xl leading-none">{template.emoji}</span>
                    <div className="flex-1">
                      <p className="text-base font-semibold">{template.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {template.description}
                      </p>
                    </div>
                  </div>
                  {template.recommended_tools.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {template.recommended_tools.slice(0, 6).map((tool) => (
                        <Badge
                          key={tool}
                          variant="outline"
                          className="text-[10px]"
                        >
                          {labelForTool(tool)}
                        </Badge>
                      ))}
                      {template.recommended_tools.length > 6 ? (
                        <Badge variant="outline" className="text-[10px]">
                          +{template.recommended_tools.length - 6}
                        </Badge>
                      ) : null}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </button>
          );
        })}
      </div>
    </div>
  );
}
