import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ButtonsWidget,
  CardWidget,
  ImageWidget,
  ListWidget,
  TableWidget,
  WidgetEventHandler,
  WidgetSpec,
} from "./types";

interface WidgetRendererProps {
  widget: WidgetSpec;
  widgetId?: string;
  messageId?: string;
  onEvent?: WidgetEventHandler;
}

export function WidgetRenderer({ widget, widgetId, messageId, onEvent }: WidgetRendererProps) {
  switch (widget.kind) {
    case "image":
      return <ImageView widget={widget} />;
    case "list":
      return <ListView widget={widget} />;
    case "table":
      return <TableView widget={widget} />;
    case "buttons":
      return (
        <ButtonsView
          widget={widget}
          widgetId={widgetId}
          messageId={messageId}
          onEvent={onEvent}
        />
      );
    case "card":
      return (
        <CardView
          widget={widget}
          widgetId={widgetId}
          messageId={messageId}
          onEvent={onEvent}
        />
      );
    default:
      return null;
  }
}

function ImageView({ widget }: { widget: ImageWidget }) {
  return (
    <figure className="overflow-hidden rounded-lg border border-border bg-muted/30">
      <img
        src={widget.src}
        alt={widget.alt ?? ""}
        className="block h-auto max-h-[420px] w-full object-contain"
        loading="lazy"
      />
      {widget.caption ? (
        <figcaption className="border-t border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
          {widget.caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

function ListView({ widget }: { widget: ListWidget }) {
  const Tag = widget.ordered ? "ol" : "ul";
  return (
    <div className="rounded-lg border border-border bg-card/60 p-3">
      {widget.title ? (
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {widget.title}
        </p>
      ) : null}
      <Tag
        className={cn(
          "space-y-1.5 pl-5 text-sm",
          widget.ordered ? "list-decimal" : "list-disc",
        )}
      >
        {widget.items.map((item, idx) => (
          <li key={item.id ?? idx} className="leading-snug">
            <span className="font-medium">{item.label}</span>
            {item.sublabel ? (
              <span className="ml-1 text-muted-foreground">— {item.sublabel}</span>
            ) : null}
          </li>
        ))}
      </Tag>
    </div>
  );
}

function TableView({ widget }: { widget: TableWidget }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="overflow-auto scrollbar-thin">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-muted/40">
            <tr>
              {widget.columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-card">
            {widget.rows.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-accent/40">
                {row.map((cell, cIdx) => (
                  <td key={cIdx} className="px-3 py-2 align-top text-foreground">
                    {cell ?? <span className="text-muted-foreground">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {widget.caption ? (
        <p className="border-t border-border bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          {widget.caption}
        </p>
      ) : null}
    </div>
  );
}

function ButtonsView({
  widget,
  widgetId,
  messageId,
  onEvent,
}: {
  widget: ButtonsWidget;
  widgetId?: string;
  messageId?: string;
  onEvent?: WidgetEventHandler;
}) {
  const handle = (actionId: string) =>
    onEvent?.({ kind: "button.pressed", actionId, widgetId, messageId });

  return (
    <div className="rounded-lg border border-border bg-card/60 p-3">
      {widget.prompt ? (
        <p className="mb-2 text-sm text-muted-foreground">{widget.prompt}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {widget.actions.map((action) => (
          <Button
            key={action.id}
            type="button"
            size="sm"
            disabled={action.disabled}
            variant={
              action.variant === "outline"
                ? "outline"
                : action.variant === "ghost"
                  ? "ghost"
                  : action.variant === "destructive"
                    ? "destructive"
                    : "default"
            }
            onClick={() => handle(action.id)}
          >
            {action.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

function CardView({
  widget,
  widgetId,
  messageId,
  onEvent,
}: {
  widget: CardWidget;
  widgetId?: string;
  messageId?: string;
  onEvent?: WidgetEventHandler;
}) {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-card/60 p-3">
      {widget.title ? (
        <p className="text-sm font-semibold">{widget.title}</p>
      ) : null}
      {widget.body ? (
        <p className="text-sm text-muted-foreground">{widget.body}</p>
      ) : null}
      {widget.widgets?.map((child, idx) => (
        <WidgetRenderer
          key={idx}
          widget={child}
          widgetId={widgetId}
          messageId={messageId}
          onEvent={onEvent}
        />
      ))}
    </div>
  );
}
