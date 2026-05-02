/**
 * Lightweight, A2UI-inspired widget contract for chat messages.
 *
 * The shape is intentionally close to https://a2ui.org/ so that backend
 * adapters can later be added without a UI rewrite. For now it is purely a
 * UI-level concept: backend streams plain text + tool calls, and rich content
 * is opt-in via the `parts` field on a chat message.
 */

export interface ImageWidget {
  kind: "image";
  src: string;
  alt?: string;
  caption?: string;
}

export interface ListWidget {
  kind: "list";
  ordered?: boolean;
  items: { id?: string; label: string; sublabel?: string }[];
  title?: string;
}

export interface TableWidget {
  kind: "table";
  columns: string[];
  rows: (string | number | null)[][];
  caption?: string;
}

export interface ButtonAction {
  id: string;
  label: string;
  variant?: "primary" | "outline" | "ghost" | "destructive";
  disabled?: boolean;
}

export interface ButtonsWidget {
  kind: "buttons";
  prompt?: string;
  actions: ButtonAction[];
}

export interface CardWidget {
  kind: "card";
  title?: string;
  body?: string;
  widgets?: WidgetSpec[];
}

export type WidgetSpec =
  | ImageWidget
  | ListWidget
  | TableWidget
  | ButtonsWidget
  | CardWidget;

export type MessagePart =
  | { type: "text"; text: string }
  | { type: "widget"; widget: WidgetSpec; widgetId?: string };

export interface WidgetEvent {
  kind: "button.pressed";
  actionId: string;
  widgetId?: string;
  messageId?: string;
}

export type WidgetEventHandler = (event: WidgetEvent) => void;
