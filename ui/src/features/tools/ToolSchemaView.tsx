import { Badge } from "@/components/ui/badge";

interface SchemaProperty {
  type?: string | string[];
  description?: string;
  enum?: unknown[];
  default?: unknown;
  items?: SchemaProperty;
  properties?: Record<string, SchemaProperty>;
}

function renderType(prop: SchemaProperty): string {
  if (Array.isArray(prop.type)) return prop.type.join(" | ");
  if (prop.enum && prop.enum.length) return prop.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (prop.type === "array" && prop.items) {
    return `${renderType(prop.items)}[]`;
  }
  return prop.type ?? "any";
}

interface Props {
  schema: Record<string, unknown> | undefined;
}

export function ToolSchemaView({ schema }: Props) {
  if (!schema || typeof schema !== "object") {
    return <p className="text-sm text-muted-foreground">No parameters.</p>;
  }
  const props = (schema as { properties?: Record<string, SchemaProperty> }).properties ?? {};
  const required = ((schema as { required?: string[] }).required ?? []) as string[];

  const entries = Object.entries(props);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No parameters.</p>;
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Name</th>
            <th className="px-3 py-2 text-left font-medium">Type</th>
            <th className="px-3 py-2 text-left font-medium">Description</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([name, prop]) => (
            <tr key={name} className="border-t border-border align-top">
              <td className="px-3 py-2 font-mono text-xs">
                <div className="flex items-center gap-1.5">
                  <span>{name}</span>
                  {required.includes(name) ? (
                    <Badge variant="outline" className="px-1 py-0 text-[10px]">
                      required
                    </Badge>
                  ) : null}
                </div>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                {renderType(prop)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {prop.description ?? "—"}
                {prop.default !== undefined ? (
                  <span className="ml-2 italic">(default: {JSON.stringify(prop.default)})</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
