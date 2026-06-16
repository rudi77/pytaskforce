import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Add16Regular,
  ArrowRight16Regular,
  Chat16Regular,
  Search20Regular,
} from "@fluentui/react-icons";

import { useConversations, useCreateConversation } from "@/api/queries";
import { cn } from "@/lib/utils";

/**
 * Cmd/Ctrl-K command palette — the "find anything" affordance.
 *
 * Lists quick actions (New task + every nav target) and all
 * conversations, filterable as you type, with arrow-key navigation.
 * Open/close state is owned by AppShell (it binds the global shortcut);
 * this component only renders + handles in-palette interaction.
 */

export interface PaletteNavTarget {
  to: string;
  label: string;
}

interface Command {
  id: string;
  label: string;
  hint: string;
  icon: React.ReactNode;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  navTargets: PaletteNavTarget[];
}

export function CommandPalette({ open, onClose, navTargets }: CommandPaletteProps) {
  const navigate = useNavigate();
  const create = useCreateConversation();
  const conversations = useConversations();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => {
      onClose();
      navigate(to);
    };
    const actions: Command[] = [
      {
        id: "action:new-task",
        label: "New task",
        hint: "Action",
        icon: <Add16Regular />,
        run: async () => {
          onClose();
          try {
            const conv = await create.mutateAsync({ channel: "rest" });
            navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
          } catch {
            navigate("/chat");
          }
        },
      },
      ...navTargets.map((n) => ({
        id: `nav:${n.to}`,
        label: n.label,
        hint: "Go to",
        icon: <ArrowRight16Regular />,
        run: go(n.to),
      })),
    ];
    const convCommands: Command[] = (conversations.data ?? [])
      .slice(0, 50)
      .map((c) => ({
        id: `conv:${c.conversation_id}`,
        label: c.topic || c.channel || c.conversation_id,
        hint: "Conversation",
        icon: <Chat16Regular />,
        run: () => {
          onClose();
          navigate(`/chat/${encodeURIComponent(c.conversation_id)}`);
        },
      }));
    return [...actions, ...convCommands];
  }, [navTargets, conversations.data, create, navigate, onClose]);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? commands.filter((cmd) => cmd.label.toLowerCase().includes(q))
    : commands;

  // Reset query + selection each time the palette opens, and focus the input.
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      // Focus after the portal paints.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Clamp the active row whenever the filtered set shrinks.
  useEffect(() => {
    setActiveIndex((i) => Math.min(i, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  // Keep the active row visible.
  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${activeIndex}"]`,
    );
    node?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) return null;

  const onKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      filtered[activeIndex]?.run();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-[120] flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-lg border border-border bg-card shadow-lg"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search20Regular className="shrink-0 text-muted-foreground" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations and actions…"
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            aria-label="Search conversations and actions"
          />
        </div>
        <div ref={listRef} className="max-h-[50vh] overflow-auto scrollbar-thin p-1.5">
          {filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              No matches.
            </p>
          ) : (
            filtered.map((cmd, i) => (
              <button
                key={cmd.id}
                type="button"
                data-index={i}
                onClick={cmd.run}
                onMouseMove={() => setActiveIndex(i)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                  i === activeIndex
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="shrink-0 text-muted-foreground">{cmd.icon}</span>
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {cmd.label}
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground/70">
                  {cmd.hint}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
