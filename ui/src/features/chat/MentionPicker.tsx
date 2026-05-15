import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  CornerDownLeft,
  File as FileIcon,
  Folder,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useWorkspaceBrowse, type WorkspaceEntry } from "@/api/queries";
import { cn } from "@/lib/utils";

/**
 * State the picker needs to operate. ``query`` is the partial text the
 * user has typed after the ``@`` trigger; ``onPick`` inserts the selected
 * path back into the prompt and ``onDismiss`` closes the popover (Escape,
 * click-outside, etc).
 */
interface MentionPickerProps {
  open: boolean;
  query: string;
  onPick: (entry: WorkspaceEntry) => void;
  onDismiss: () => void;
}

/**
 * Cowork-style ``@mention`` file picker.
 *
 * Behaviour:
 *
 *   - Lists files and directories from the workspace root (set via
 *     ``TASKFORCE_WORKSPACE_ROOT`` env or falls back to ``cwd``).
 *   - Type-to-narrow: the picker forwards ``query`` to the backend's ``q``
 *     param so filtering works even in large repos without shipping the
 *     full tree to the browser.
 *   - Click or Enter on a FILE inserts ``@<relative/path>`` into the
 *     prompt — the agent reads the file lazily via ``file_read`` when it
 *     needs the contents (matches Cowork semantics: @mention only marks
 *     intent; it doesn't pre-load content).
 *   - Click or Enter on a DIR drills in; backspace / ChevronLeft goes
 *     back up. The popover keeps a tiny breadcrumb of the current dir.
 *   - Arrow keys move selection; Escape dismisses.
 *
 * The popover is intentionally **not** a Radix Popover — it's an absolutely-
 * positioned floating panel that the host (``ChatComposer``) anchors above
 * the textarea. Using a managed Popover would steal focus from the
 * textarea, which is the opposite of what we want: the user must keep
 * typing to filter.
 */
export function MentionPicker({
  open,
  query,
  onPick,
  onDismiss,
}: MentionPickerProps) {
  const [currentPath, setCurrentPath] = useState("");
  const [highlight, setHighlight] = useState(0);
  // Track the last query that was acted upon so we can reset highlight
  // when the user keeps typing (otherwise stale index points off-list).
  const lastQueryRef = useRef(query);

  // Reset to root whenever the picker re-opens from scratch.
  useEffect(() => {
    if (open) {
      setCurrentPath("");
      setHighlight(0);
      lastQueryRef.current = query;
    }
    // Intentional: we ONLY want to react to ``open`` here, not to query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (lastQueryRef.current !== query) {
      setHighlight(0);
      lastQueryRef.current = query;
    }
  }, [query]);

  const browse = useWorkspaceBrowse({ path: currentPath, q: query }, open);
  const entries = browse.data?.entries ?? [];

  // Clamp highlight so it never points past the end (entries change as
  // the user types or drills into subdirs).
  const safeHighlight = useMemo(
    () => (entries.length === 0 ? 0 : Math.min(highlight, entries.length - 1)),
    [highlight, entries.length],
  );

  // Listen for keyboard navigation at the window level so the textarea
  // doesn't have to forward events. Active only while ``open`` is true.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight((h) => (entries.length === 0 ? 0 : (h + 1) % entries.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight((h) =>
          entries.length === 0 ? 0 : (h - 1 + entries.length) % entries.length,
        );
      } else if (e.key === "Enter") {
        const entry = entries[safeHighlight];
        if (entry) {
          e.preventDefault();
          activate(entry);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onDismiss();
      } else if (e.key === "Backspace" && query === "" && currentPath) {
        // Empty query + Backspace ⇒ go up one level. Lets the user keep
        // typing forward through the tree without reaching for the mouse.
        e.preventDefault();
        goUp();
      }
    };
    window.addEventListener("keydown", handler, { capture: true });
    return () => window.removeEventListener("keydown", handler, { capture: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, entries, safeHighlight, query, currentPath]);

  const activate = (entry: WorkspaceEntry) => {
    if (entry.type === "dir") {
      setCurrentPath(entry.path);
      setHighlight(0);
    } else {
      onPick(entry);
    }
  };

  const goUp = () => {
    if (!currentPath) return;
    const idx = currentPath.lastIndexOf("/");
    setCurrentPath(idx === -1 ? "" : currentPath.slice(0, idx));
    setHighlight(0);
  };

  if (!open) return null;

  return (
    <div
      role="listbox"
      aria-label="Workspace file picker"
      className={cn(
        "z-30 w-full max-w-md overflow-hidden rounded-lg border border-border bg-popover shadow-lg",
      )}
    >
      <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
        {currentPath ? (
          <button
            type="button"
            onClick={goUp}
            className="flex items-center gap-0.5 rounded px-1 py-0.5 hover:bg-accent"
            aria-label="Go up one directory"
          >
            <ChevronLeft className="h-3 w-3" />
          </button>
        ) : (
          <span aria-hidden className="h-4 w-4" />
        )}
        <span className="truncate font-mono text-[11px]">
          {currentPath || "/"}
        </span>
        {browse.data?.truncated ? (
          <Badge variant="outline" className="ml-auto px-1 py-0 text-[9px]">
            partial — type to narrow
          </Badge>
        ) : null}
      </div>

      <ul className="max-h-72 overflow-auto scrollbar-thin py-1">
        {browse.isLoading ? (
          <li className="px-3 py-2 text-xs text-muted-foreground">Loading…</li>
        ) : browse.isError ? (
          <li className="px-3 py-2 text-xs text-destructive">
            Failed to load workspace.
          </li>
        ) : entries.length === 0 ? (
          <li className="px-3 py-2 text-xs text-muted-foreground">
            No matches in this directory.
          </li>
        ) : (
          entries.map((entry, idx) => (
            <li key={entry.path}>
              <button
                type="button"
                onMouseDown={(e) => {
                  // ``mousedown`` (not ``click``) so the textarea doesn't
                  // lose focus during the pick — losing focus would close
                  // the picker before the click fires.
                  e.preventDefault();
                  activate(entry);
                }}
                onMouseEnter={() => setHighlight(idx)}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
                  idx === safeHighlight
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/60",
                )}
              >
                {entry.type === "dir" ? (
                  <Folder className="h-3.5 w-3.5 text-amber-500" />
                ) : (
                  <FileIcon className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <span className="truncate font-mono">{entry.name}</span>
                {entry.type === "dir" ? (
                  <span className="text-muted-foreground/60">/</span>
                ) : null}
                {entry.type === "file" && typeof entry.size === "number" ? (
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    {formatSize(entry.size)}
                  </span>
                ) : null}
              </button>
            </li>
          ))
        )}
      </ul>

      <div className="flex items-center justify-between border-t border-border bg-muted/40 px-2 py-1 text-[10px] text-muted-foreground">
        <span>↑↓ navigate · Enter pick · Backspace up</span>
        <span className="inline-flex items-center gap-1">
          <CornerDownLeft className="h-3 w-3" />
          Esc to close
        </span>
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
