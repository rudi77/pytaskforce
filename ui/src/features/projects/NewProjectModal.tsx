import { useEffect, useState } from "react";
import { FolderPlus, FolderOpen, FolderSearch, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/api/client";
import {
  useCreateProject,
  type CreateProjectMode,
  type Project,
} from "@/api/queries";
import { cn } from "@/lib/utils";
import { FolderBrowserPanel } from "./FolderBrowserPanel";

interface Props {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated?: (project: Project) => void;
}

type Step = "choose" | "form" | "browse";

interface ModeMeta {
  key: CreateProjectMode;
  title: string;
  description: string;
  pathHint: string;
  icon: typeof FolderPlus;
}

const MODES: ModeMeta[] = [
  {
    key: "scratch",
    title: "Von Grund auf neu beginnen",
    description:
      "Richte einen neuen Ordner mit CLAUDE.md und skills/ ein. Wenn der Ordner nicht existiert, wird er angelegt.",
    pathHint: "/home/user/projects/mein-projekt",
    icon: FolderPlus,
  },
  {
    key: "existing",
    title: "Vorhandenen Ordner verwenden",
    description:
      "Zeige Claude auf ein Verzeichnis, mit dem du bereits arbeitest. CLAUDE.md und skills/ werden ergänzt, falls sie fehlen — bestehende Dateien bleiben unangetastet.",
    pathHint: "/home/user/Projects/TuttiPaletti",
    icon: FolderOpen,
  },
];

export function NewProjectModal({ open, onOpenChange, onCreated }: Props) {
  const [step, setStep] = useState<Step>("choose");
  const [mode, setMode] = useState<CreateProjectMode>("scratch");
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useCreateProject();

  // Reset modal state every time it opens, so the user doesn't see
  // stale inputs after a cancel.
  useEffect(() => {
    if (open) {
      setStep("choose");
      setMode("scratch");
      setName("");
      setPath("");
      setError(null);
    }
  }, [open]);

  const chooseMode = (next: CreateProjectMode) => {
    setMode(next);
    setStep("form");
    setError(null);
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const trimmedName = name.trim();
    const trimmedPath = path.trim();
    if (!trimmedName || !trimmedPath) {
      setError("Name und Pfad sind erforderlich.");
      return;
    }
    try {
      const project = await create.mutateAsync({
        name: trimmedName,
        path: trimmedPath,
        mode,
      });
      onOpenChange(false);
      onCreated?.(project);
    } catch (err) {
      if (err instanceof ApiError) {
        const resolved =
          typeof err.details === "object" && err.details !== null
            ? (err.details as { path?: string }).path
            : undefined;
        setError(
          resolved && resolved !== trimmedPath
            ? `${err.message} (aufgelöst zu: ${resolved})`
            : err.message,
        );
      } else {
        setError(
          (err as Error).message || "Projekt konnte nicht erstellt werden.",
        );
      }
    }
  };

  const activeMeta = MODES.find((m) => m.key === mode) ?? MODES[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        {step === "browse" ? (
          <>
            <DialogHeader>
              <DialogTitle>Ordner auswählen</DialogTitle>
              <DialogDescription>
                Navigiere durch dein Dateisystem oder tippe einen Pfad direkt
                ein. Doppelklick öffnet einen Ordner.
              </DialogDescription>
            </DialogHeader>
            <FolderBrowserPanel
              initialPath={path}
              onCancel={() => setStep("form")}
              onSelect={(chosen) => {
                setPath(chosen);
                setStep("form");
              }}
            />
          </>
        ) : step === "choose" ? (
          <>
            <DialogHeader>
              <DialogTitle>Neues Projekt erstellen</DialogTitle>
              <DialogDescription>
                Ein eigener Ort für laufende Arbeiten, bei dem sich der Kontext
                im Laufe der Zeit aufbaut. Dateien und Anweisungen bleiben in
                einem Ordner auf deinem Computer.
              </DialogDescription>
            </DialogHeader>
            <ul className="flex flex-col gap-2">
              {MODES.map((m) => {
                const Icon = m.icon;
                return (
                  <li key={m.key}>
                    <button
                      type="button"
                      onClick={() => chooseMode(m.key)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-lg border border-border bg-background px-4 py-3 text-left transition-colors",
                        "hover:border-primary/40 hover:bg-accent/40",
                      )}
                    >
                      <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
                        <Icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-foreground">
                          {m.title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {m.description}
                        </p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={onSubmit}>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <activeMeta.icon className="h-4 w-4 text-muted-foreground" />
                <DialogTitle>{activeMeta.title}</DialogTitle>
              </div>
              <DialogDescription>{activeMeta.description}</DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project-name">Name</Label>
              <Input
                id="project-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="TuttiPaletti"
                autoFocus
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project-path">Verzeichnis</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="project-path"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder={activeMeta.pathHint}
                  spellCheck={false}
                  required
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setStep("browse")}
                >
                  <FolderSearch className="h-4 w-4" />
                  Durchsuchen…
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Absoluter Pfad. {mode === "scratch"
                  ? "Wenn das Verzeichnis nicht existiert, wird es angelegt."
                  : "Das Verzeichnis muss bereits existieren."}
              </p>
            </div>

            {error ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            ) : null}

            <div className="flex items-center justify-between gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStep("choose")}
              >
                <X className="h-4 w-4" />
                Zurück
              </Button>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => onOpenChange(false)}
                >
                  Abbrechen
                </Button>
                <Button type="submit" disabled={create.isPending}>
                  {create.isPending ? "Lege an…" : "Projekt erstellen"}
                </Button>
              </div>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
