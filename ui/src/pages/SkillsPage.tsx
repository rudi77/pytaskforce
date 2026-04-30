import { useMemo, useState } from "react";
import { Search, Sparkles } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import {
  useSkill,
  useSkills,
  type SkillSummary,
} from "@/api/queries";
import { cn } from "@/lib/utils";

const TYPE_VARIANT: Record<
  string,
  "default" | "secondary" | "outline" | "warning"
> = {
  context: "secondary",
  prompt: "default",
  agent: "warning",
  library: "outline",
  integration: "outline",
};

export default function SkillsPage() {
  const skills = useSkills();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [active, setActive] = useState<string | null>(null);

  const items = skills.data?.skills ?? [];

  const types = useMemo(() => {
    const set = new Set<string>();
    for (const s of items) set.add(s.skill_type);
    return ["all", ...Array.from(set).sort()];
  }, [items]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return items.filter((skill) => {
      if (typeFilter !== "all" && skill.skill_type !== typeFilter) return false;
      if (!needle) return true;
      return [skill.name, skill.description, skill.slash_name ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [items, typeFilter, search]);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <Card className="lg:sticky lg:top-4 lg:self-start">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Skills
          </CardTitle>
          <CardDescription>
            File-based capabilities. Click any skill to preview its SKILL.md.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="pl-8"
            />
          </div>
          <div className="flex flex-wrap gap-1 rounded-md bg-muted p-1 text-xs">
            {types.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTypeFilter(t)}
                className={cn(
                  "rounded px-2.5 py-1 font-medium transition-colors",
                  typeFilter === t
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t}
              </button>
            ))}
          </div>

          {skills.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : skills.error ? (
            <EmptyState
              title="Could not load skills"
              description={
                skills.error instanceof ApiError
                  ? skills.error.message
                  : "Backend returned an error."
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No matching skills"
              description="Try a different search term or filter."
            />
          ) : (
            <ul className="space-y-1">
              {filtered.map((skill) => (
                <SkillRow
                  key={skill.name}
                  skill={skill}
                  active={skill.name === active}
                  onSelect={() => setActive(skill.name)}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <SkillDetailView name={active ?? undefined} />
    </div>
  );
}

function SkillRow({
  skill,
  active,
  onSelect,
}: {
  skill: SkillSummary;
  active: boolean;
  onSelect: () => void;
}) {
  const variant = TYPE_VARIANT[skill.skill_type] ?? "secondary";
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex w-full flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors",
          active
            ? "border-primary/40 bg-primary/5"
            : "border-transparent hover:border-border hover:bg-accent/40",
        )}
      >
        <div className="flex w-full items-center gap-2">
          <span className="truncate font-medium">{skill.name}</span>
          <Badge variant={variant} className="ml-auto px-1.5 py-0 text-[10px]">
            {skill.skill_type}
          </Badge>
        </div>
        {skill.description ? (
          <span className="line-clamp-2 text-xs text-muted-foreground">
            {skill.description}
          </span>
        ) : null}
        {skill.slash_name ? (
          <span className="text-[10px] font-mono text-muted-foreground">
            /{skill.slash_name}
          </span>
        ) : null}
      </button>
    </li>
  );
}

function SkillDetailView({ name }: { name: string | undefined }) {
  const detail = useSkill(name);

  if (!name) {
    return (
      <Card>
        <CardContent className="flex h-72 items-center justify-center">
          <EmptyState
            title="Pick a skill"
            description="Select a skill on the left to see its SKILL.md content."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{detail.data?.name ?? name}</CardTitle>
        <CardDescription>
          {detail.data?.description}
          {detail.data?.file_path ? (
            <span className="block font-mono text-[10px] text-muted-foreground">
              {detail.data.file_path}
            </span>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {detail.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : detail.error ? (
          <EmptyState
            title="Could not load skill"
            description={
              detail.error instanceof ApiError
                ? detail.error.message
                : "Unknown error"
            }
          />
        ) : (
          <pre className="max-h-[640px] overflow-auto scrollbar-thin whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 text-xs leading-relaxed">
            {detail.data?.body || "(this skill has no body content)"}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
