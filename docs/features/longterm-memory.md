# Long-Term Memory

**Version:** 2.0
**Status:** Production-Ready
**Backend:** Unified Memory Service (file-based Markdown store)

---

## Overview

Taskforce agents maintain **persistent memory across sessions** using a unified memory service. Memory records are stored as Markdown files with YAML front matter and are **profile-specific**, so each agent profile (coding, rag, etc.) retains its own isolated memory store.

This enables agents to:

- Remember user preferences and working styles
- Track project context and architectural decisions
- Build cumulative knowledge across conversations
- Provide personalized and context-aware responses

---

## Architecture

### Memory Record Model

Each memory entry is a **record** with structured metadata and Markdown content:

- **scope**: `session`, `profile`, `user`, `org`
- **kind**: `short_term`, `long_term`, `tool_result`, `epic_log`
- **tags**: list of keywords for filtering/search
- **content**: Markdown body
- **metadata**: free-form JSON-compatible context

### Storage Backend

- **Format:** Markdown (`.md`) with YAML front matter
- **Location:** Profile-specific (default: `<work_dir>/memory`)
- **Persistence:** File-based, survives agent restarts and system reboots
- **Isolation:** Separate store per profile/work dir

---

## Configuration

### Enable Memory for a Profile

Add the `memory` section and the `memory` tool to your profile YAML:

```yaml
# configs/coding_agent.yaml

profile: coding_agent
specialist: coding

persistence:
  type: file
  work_dir: .taskforce_coding

# Enable unified memory
memory:
  type: file
  store_dir: .taskforce_coding/memory

tools:
  - python
  - file_read
  - memory
```

**Key Configuration Fields:**

| Field | Description |
|-------|-------------|
| `memory.type` | `file` (default file-backed store) |
| `memory.store_dir` | Directory for Markdown memory records |
| `tools` | Include `memory` to expose the unified memory tool |

---

## Memory Tool

The unified `memory` tool provides CRUD operations over memory records.

### Core Actions

**`add`** — store a memory record

```json
{
  "action": "add",
  "scope": "profile",
  "kind": "long_term",
  "tags": ["decision", "architecture"],
  "content": "We standardized on file-backed memory with Markdown records.",
  "metadata": {"source": "design-review"}
}
```

**`search`** — full-text search over memory content and tags

```json
{
  "action": "search",
  "scope": "profile",
  "kind": "long_term",
  "query": "architecture",
  "limit": 5
}
```

**`list`** — list records by scope/kind

```json
{
  "action": "list",
  "scope": "profile",
  "kind": "long_term"
}
```

**`get`** — fetch a record by id

```json
{
  "action": "get",
  "record_id": "<id>"
}
```

**`update`** — overwrite an existing record

```json
{
  "action": "update",
  "record_id": "<id>",
  "scope": "profile",
  "kind": "long_term",
  "tags": ["decision"],
  "content": "Updated memory content",
  "metadata": {"source": "retrospective"}
}
```

**`delete`** — remove a record by id

```json
{
  "action": "delete",
  "record_id": "<id>"
}
```

---

## Best Practices

✅ **At conversation start:** search memory for relevant context

✅ **When learning:** write important decisions, preferences, and constraints

✅ **When unsure:** search memory before asking repeated questions

✅ **Use tags:** make future retrieval easy (`decision`, `preference`, `bugfix`, `infra`)

---

## Troubleshooting

**Symptom:** memory records are not appearing

1. Verify the `memory` tool is enabled in the profile.
2. Check `memory.store_dir` points to a writable directory.
3. Confirm the profile `work_dir` exists and is writable.

---

## Roadmap

- [ ] Automatic summarization/compaction of older records
- [ ] Optional vector index for semantic recall
- [ ] Multi-user memory with access control
- [ ] Web UI for memory visualization
