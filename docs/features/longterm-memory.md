# Long-Term Memory

**Version:** 1.0
**Status:** Production-Ready
**MCP Server:** [@modelcontextprotocol/server-memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)

---

## Overview

Taskforce agents can maintain **persistent memory across sessions** using the Knowledge Graph Memory MCP Server. This enables agents to:

- Remember user preferences and working styles
- Track project context and architectural decisions
- Build cumulative knowledge over multiple conversations
- Provide personalized and context-aware responses

Memory is **profile-specific** - each agent profile (coding, rag, etc.) maintains its own isolated knowledge graph.

---

## Architecture

### Knowledge Graph Structure

The memory system uses a graph-based data model with three core concepts:

```
┌─────────────┐
│   Entity    │ ← Nodes (User, Project, Tool, Pattern, Decision)
│   - name    │
│   - type    │
│   - observations []
└──────┬──────┘
       │
       │ ┌──────────────┐
       ├─┤  Relation    │ ← Edges (works_on, uses, depends_on)
       │ │  - from      │
       │ │  - to        │
       │ │  - type      │
       │ └──────────────┘
       │
       ▼
┌─────────────┐
│ Observation │ ← Atomic facts attached to entities
│  "string"   │
└─────────────┘
```

**Entity**: Primary node representing people, projects, tools, patterns, or decisions
**Relation**: Directed connection between entities (e.g., "Alice works_on ProjectX")
**Observation**: Discrete, atomic fact attached to an entity (e.g., "Prefers Python over JavaScript")

### Storage Backend

- **Format:** JSONL (JSON Lines) file
- **Location:** Profile-specific (e.g., `.taskforce_coding/.memory/knowledge_graph.jsonl`)
- **Persistence:** File-based, survives agent restarts and system reboots
- **Concurrency:** Managed by MCP server (single-writer, multi-reader)

---

## Configuration

### Enable Memory for a Profile

Add the `mcp_servers` configuration to your profile YAML:

```yaml
# configs/coding_agent.yaml

profile: coding_agent
specialist: coding

persistence:
  type: file
  work_dir: .taskforce_coding

# Enable long-term memory
mcp_servers:
  - type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-memory"
    env:
      MEMORY_FILE_PATH: ".taskforce_coding/.memory/knowledge_graph.jsonl"
    description: "Long-term knowledge graph memory"
```

**Key Configuration Fields:**

| Field | Description |
|-------|-------------|
| `type` | `stdio` (local subprocess) |
| `command` | `npx` (Node.js package executor) |
| `args` | Package name and flags |
| `env.MEMORY_FILE_PATH` | Path to JSONL memory file (auto-created) |

### Prerequisites

- **Node.js:** v18+ (Memory server runs via NPM)
- **NPM:** v9+ (for `npx` command)

The MCP Memory Server is automatically downloaded on first use (no manual installation needed).

---

## Available Tools

Once configured, the agent gains access to 9 memory tools:

### Core Operations

**`create_entities`**
Create new entities in the knowledge graph.

```json
{
  "entities": [
    {
      "name": "Alice",
      "entityType": "User",
      "observations": ["Prefers Python", "Senior Backend Engineer"]
    }
  ]
}
```

**`create_relations`**
Create directed relationships between entities.

```json
{
  "relations": [
    {
      "from": "Alice",
      "to": "TaskforceProject",
      "relationType": "contributes_to"
    }
  ]
}
```

**`add_observations`**
Add new facts to an existing entity.

```json
{
  "entityName": "TaskforceProject",
  "observations": [
    "Uses Clean Architecture",
    "Built with Python 3.11"
  ]
}
```

### Query Operations

**`read_graph`**
Retrieve the entire knowledge graph (all entities and relations).

**`search_nodes`**
Search for entities by name, type, or observation content.

```json
{
  "query": "Python"
}
```

**`open_nodes`**
Retrieve specific entities by name.

```json
{
  "names": ["Alice", "TaskforceProject"]
}
```

### Deletion Operations

**`delete_entities`**
Remove entities (and their relations) from the graph.

```json
{
  "entityNames": ["ObsoleteProject"]
}
```

**`delete_observations`**
Remove specific observations from an entity.

```json
{
  "entityName": "Alice",
  "observations": ["Outdated preference"]
}
```

**`delete_relations`**
Remove specific relationships.

```json
{
  "relations": [
    {
      "from": "Alice",
      "to": "OldProject",
      "relationType": "worked_on"
    }
  ]
}
```

---

## Usage Patterns

### Pattern 1: User Preference Tracking

**Scenario:** Remember user's coding style and preferences

```python
# First conversation - Agent learns
User: "I prefer using type hints in Python and avoid abbreviations"
Agent: <stores in memory>

create_entities([{
  "name": "User_Alice",
  "entityType": "User",
  "observations": [
    "Prefers type hints in Python",
    "Avoids abbreviations in variable names"
  ]
}])
```

**Later conversation:**

```python
# Agent recalls preference
Agent: <at start, reads memory>
read_graph()
# Finds User_Alice preferences

Agent: "I'll write the function with full type hints as you prefer..."
```

### Pattern 2: Project Context Memory

**Scenario:** Track project architecture and decisions

```python
# Store project info
create_entities([{
  "name": "TaskforceProject",
  "entityType": "Project",
  "observations": [
    "Uses Clean Architecture pattern",
    "Layer order: Core → Infrastructure → Application → API",
    "uv for package management (NOT pip)"
  ]
}])

create_relations([{
  "from": "TaskforceProject",
  "to": "Python",
  "relationType": "written_in"
}])
```

### Pattern 3: Learning from Past Issues

**Scenario:** Remember solutions to recurring problems

```python
# First time encountering issue
User: "Git push fails with 403"
Agent: <solves issue>

add_observations("TaskforceProject", [
  "Git push requires branch name format: claude/*-sessionId",
  "Push failures solved by checking branch naming convention"
])
```

**Next time:**

```python
# Agent searches memory before debugging
search_nodes("git push 403")
# Finds previous solution
Agent: "This looks like the branch naming issue we solved before..."
```

### Pattern 4: Code Pattern Recognition

**Scenario:** Track coding patterns used in the project

```python
create_entities([{
  "name": "ErrorHandling_Pattern",
  "entityType": "Pattern",
  "observations": [
    "Use specific exceptions (ValueError, HTTPException)",
    "Always include contextual error messages",
    "Log errors with structlog before re-raising"
  ]
}])

create_relations([{
  "from": "TaskforceProject",
  "to": "ErrorHandling_Pattern",
  "relationType": "follows"
}])
```

---

## Best Practices

### 1. Atomic Observations

❌ **Bad:** Compound facts
```json
"observations": ["Alice is a Senior Engineer who prefers Python and works remotely"]
```

✅ **Good:** One fact per observation
```json
"observations": [
  "Senior Backend Engineer",
  "Prefers Python",
  "Works remotely"
]
```

### 2. Active Voice Relations

❌ **Bad:** Passive voice
```json
{
  "from": "ProjectX",
  "to": "Alice",
  "relationType": "is_led_by"
}
```

✅ **Good:** Active voice
```json
{
  "from": "Alice",
  "to": "ProjectX",
  "relationType": "leads"
}
```

### 3. Consistent Entity Names

❌ **Bad:** Variations
```json
"Alice", "alice", "Alice Smith", "A. Smith"
```

✅ **Good:** Canonical names
```json
"Alice_Smith"  // Consistent identifier
```

### 4. Regular Memory Retrieval

✅ **At conversation start:**
```python
# Always check for existing context
result = search_nodes("user preferences")
if result["entities"]:
    # Use context to personalize response
    ...
```

### 5. Cleanup Outdated Information

✅ **Maintain memory hygiene:**
```python
# When learning something new that contradicts old info
delete_observations("Alice_Smith", ["Prefers Java"])
add_observations("Alice_Smith", ["Prefers Python"])
```

---

## Agent Behavior

The agent is instructed via system prompt to:

1. **At conversation start:** Check memory for relevant context
2. **During execution:** Monitor for memorable information
3. **When learning:** Update memory with new facts
4. **When unsure:** Search memory before asking user

**What the agent remembers:**
- User identity and preferences
- Project architecture and decisions
- Code patterns and conventions
- Past issues and solutions
- Goals and requirements

---

## Troubleshooting

### Memory Directory Not Created

**Symptom:** Agent starts but no `.memory/` directory appears

**Solution:**
1. Check Node.js/NPM installation: `node --version`
2. Verify `MEMORY_FILE_PATH` in config is writable
3. Check agent logs for MCP connection errors

### Memory Server Connection Failed

**Symptom:** Agent logs show "mcp_server_connection_failed"

**Solution:**
1. Ensure NPM can access network (for first-time package download)
2. Check firewall/proxy settings
3. Try manual install: `npm install -g @modelcontextprotocol/server-memory`

### Memory Not Persisting

**Symptom:** Knowledge graph resets between sessions

**Solution:**
1. Verify `MEMORY_FILE_PATH` points to persistent location (not `/tmp`)
2. Check file permissions on `.memory/` directory
3. Ensure agent has write access to memory file

### Tools Not Available

**Symptom:** `create_entities` tool not found

**Solution:**
1. Verify `mcp_servers` config syntax (must be list, not dict)
2. Check agent logs for MCP server startup errors
3. Test MCP server manually: `npx -y @modelcontextprotocol/server-memory`

---

## Performance Considerations

### Memory File Size

- **Typical size:** 10-100 KB per profile (hundreds of entities)
- **Large graph:** 1-5 MB (thousands of entities, still performant)
- **No automatic cleanup:** Consider periodic pruning for very long-term use

### Query Performance

- **read_graph:** Fast (< 50ms) for graphs up to 10,000 entities
- **search_nodes:** Uses in-memory search, performant for typical use
- **Recommendation:** Keep graphs focused (< 5,000 entities per profile)

### Session Startup

- **First load:** +100-200ms (MCP server startup)
- **Subsequent loads:** +20-50ms (memory file read)
- **Impact:** Negligible for typical interactive sessions

---

## Examples

### Complete Workflow: User Onboarding

```python
# Session 1: First interaction
User: "Hi, I'm Alice. I work on backend services and prefer Python with type hints."

Agent:
# Store user info
create_entities([{
  "name": "Alice",
  "entityType": "User",
  "observations": [
    "Works on backend services",
    "Prefers Python",
    "Uses type hints"
  ]
}])

# Session 2: Return visit
Agent:
# Retrieve memory at start
user_info = search_nodes("Alice")
# Found: Works on backend services, Prefers Python, Uses type hints

Agent: "Welcome back, Alice! Ready to work on more backend code?"

# Session 3: Learn more
User: "I also prefer using uv over pip for package management"

Agent:
add_observations("Alice", ["Prefers uv over pip"])
```

---

## Security & Privacy

- **Local Storage:** Memory files stored locally, not in cloud
- **No External API:** MCP server runs as local subprocess
- **Profile Isolation:** Each profile has separate memory (no cross-contamination)
- **No Encryption:** Memory files are plaintext JSONL (encrypt disk if needed)

---

## Limitations

1. **No automatic pruning:** Memory grows indefinitely (manual cleanup required)
2. **Single-file storage:** Not suitable for massive graphs (> 100K entities)
3. **No versioning:** No built-in rollback for memory changes
4. **No semantic search:** Search is text-based, not embedding-based

---

## Future Enhancements (Roadmap)

- [ ] Automatic memory summarization (compress old observations)
- [ ] Semantic search via embeddings
- [ ] Memory export/import for backup
- [ ] Web UI for memory visualization
- [ ] Multi-user memory with access control

---

## Related Documentation

- [MCP Integration Guide](../architecture/section-3-tech-stack.md)
- [Profile Configuration](../profiles.md)
- [Agent Factory](../../src/taskforce/application/factory.py)
- [System Prompts](../../src/taskforce/core/prompts/autonomous_prompts.py)

---

**Last Updated:** 2026-01-13
**Author:** Taskforce Team
