import { useEffect, useState } from "react";
import {
  ArrowSync20Regular,
  ChevronLeft20Regular,
  FolderOpen20Regular,
  Storage20Regular,
} from "@fluentui/react-icons";
import { Button, Input, Label } from "@fluentui/react-components";

import { useBrowseFilesystem } from "@/api/queries";
import { cn } from "@/lib/utils";

interface Props {
  initialPath?: string;
  onCancel: () => void;
  onSelect: (path: string) => void;
}

export function FolderBrowserPanel({
  initialPath,
  onCancel,
  onSelect,
}: Props) {
  const [path, setPath] = useState(initialPath ?? "");
  const [pathDraft, setPathDraft] = useState(initialPath ?? "");

  useEffect(() => {
    setPathDraft(path);
  }, [path]);

  const { data, isLoading, isError, error, refetch, isFetching } =
    useBrowseFilesystem(path);

  const goTo = (next: string) => setPath(next);

  const onPathSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = pathDraft.trim();
    if (trimmed) goTo(trimmed);
  };

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={onPathSubmit} className="flex items-end gap-2">
        <div className="flex flex-1 flex-col gap-1">
          <Label htmlFor="browse-path">Aktueller Pfad</Label>
          <Input
            id="browse-path"
            value={pathDraft}
            onChange={(_, data) => setPathDraft(data.value)}
            spellCheck={false}
            placeholder="Pfad eingeben oder unten auswählen"
          />
        </div>
        <Button type="submit" appearance="outline" size="small">
          Gehe zu
        </Button>
        <Button
          type="button"
          appearance="subtle"
          size="small"
          icon={
            <ArrowSync20Regular className={cn(isFetching && "animate-spin")} />
          }
          onClick={() => refetch()}
          aria-label="Aktualisieren"
          disabled={isFetching}
        />
      </form>

      {data?.is_windows && data.drives.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {data.drives.map((drive) => (
            <button
              key={drive}
              type="button"
              onClick={() => goTo(drive)}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs",
                "hover:border-primary/40 hover:bg-accent/40",
                data.path === drive && "border-primary bg-accent/40",
              )}
            >
              <Storage20Regular />
              {drive}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <Button
          type="button"
          appearance="outline"
          size="small"
          icon={<ChevronLeft20Regular />}
          onClick={() => data?.parent && goTo(data.parent)}
          disabled={!data?.parent}
        >
          Übergeordnet
        </Button>
        <p className="truncate text-[11px] text-muted-foreground">
          {data?.path ?? (isLoading ? "Lade…" : "")}
        </p>
      </div>

      <div className="h-64 overflow-y-auto rounded-md border border-border bg-background">
        {isError ? (
          <p className="p-3 text-xs text-destructive">
            {error?.message ?? "Verzeichnis konnte nicht geladen werden."}
          </p>
        ) : isLoading ? (
          <p className="p-3 text-xs text-muted-foreground">Lade…</p>
        ) : data && data.entries.length === 0 ? (
          <p className="p-3 text-xs text-muted-foreground">
            Keine Unterordner.
          </p>
        ) : (
          <ul className="divide-y divide-border/60">
            {data?.entries.map((entry) => (
              <li key={entry.path}>
                <button
                  type="button"
                  onDoubleClick={() => goTo(entry.path)}
                  onClick={() => setPathDraft(entry.path)}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs",
                    "hover:bg-accent/40",
                    pathDraft === entry.path && "bg-accent/40",
                  )}
                  title="Klicken zum Markieren, Doppelklick zum Öffnen"
                >
                  <FolderOpen20Regular className="text-muted-foreground" />
                  <span className="truncate">{entry.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button type="button" appearance="subtle" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button
          type="button"
          appearance="primary"
          onClick={() => {
            const chosen = (pathDraft || data?.path || "").trim();
            if (chosen) onSelect(chosen);
          }}
          disabled={!pathDraft && !data?.path}
        >
          Diesen Ordner auswählen
        </Button>
      </div>
    </div>
  );
}
