# Story: Ralph Loop Documentation & Examples - Brownfield Addition

## Purpose
Provide comprehensive documentation and a "Golden Example" for the Ralph Loop plugin to ensure successful adoption and correct usage patterns.

## User Story
As a **new user of Ralph Loop**,
I want **clear instructions and a working example**,
So that **I can set up my own autonomous development loops without confusion**.

## Story Context
- **Existing System Integration:** `docs/` folder and `examples/` directory.
- **Technology:** Markdown.
- **Follows pattern:** Existing Taskforce documentation style.
- **Touch points:** `docs/ralph.md`, `docs/index.md`, `examples/ralph_plugin/README.md`.

## Acceptance Criteria

### Functional Requirements
1. **Feature Guide:** Create `docs/ralph.md` explaining:
    - What is a Ralph Loop (The "fresh context" philosophy).
    - How to install the plugin and script.
    - How to define a task in `RALPH_TASK.md`.
    - How to monitor the loop via `activity.log`.
2. **Golden Example:** Provide a sample `RALPH_TASK.md` and `prd.json` for a simple task (e.g., "Implement a calculator with tests") in `examples/ralph_plugin/`.
3. **Guardrails Guide:** Explain how the `AGENTS.md` self-maintenance works and how to interpret "Signs".
4. **Navigation:** Link `docs/ralph.md` in `docs/index.md` under the "Advanced Patterns" or "Plugins" section.

### Integration Requirements
5. **Consistency:** Ensure the terminology (PRD, Iteration, Context Rotation, Gutter) is consistent between the code, the script, and the documentation.
6. **Troubleshooting:** Include a "Troubleshooting" section addressing common issues like "Gutter detection" and "Infinite loop prevention".

### Quality Requirements
7. **Readability:** Use Mermaid diagrams to visualize the flow (Orchestrator -> CLI -> Tools -> Git).
8. **Accuracy:** All command examples MUST be verified against the actual implementation.

## Technical Notes
- **Diagrams:** Use Mermaid for the architecture overview.
- **Format:** Ensure all Markdown files follow the project's formatting standards (headers, code blocks).

## Definition of Done
- [x] `docs/ralph.md` created and linked.
- [x] `examples/ralph_plugin/README.md` created with quick-start steps.
- [x] Example task files included in the plugin folder.
- [x] User guide verified for clarity.

## Dev Agent Record

### Agent Model Used
Claude Sonnet 4.5 (via Cursor)

### File List
- `docs/ralph.md` - Comprehensive Ralph Loop documentation guide
- `examples/ralph_plugin/README.md` - Quick start guide for Ralph plugin
- `examples/ralph_plugin/RALPH_TASK.md` - Example task description
- `examples/ralph_plugin/prd.json.example` - Example PRD structure
- `docs/index.md` - Updated with link to Ralph Loop documentation

### Completion Notes
- Created comprehensive `docs/ralph.md` with:
  - Architecture overview with Mermaid diagram
  - Installation and setup instructions
  - Quick start guide
  - Core concepts (PRD, Context Rotation, Iteration, Gutter)
  - File structure explanation
  - Configuration options
  - Troubleshooting section covering common issues
  - Best practices
  - Advanced usage patterns
  - Terminology reference
- Created `examples/ralph_plugin/README.md` with quick-start steps
- Created example files:
  - `RALPH_TASK.md` - Example calculator task description
  - `prd.json.example` - Example PRD with 5 user stories
- Updated `docs/index.md` to link Ralph Loop under "Advanced Patterns" section
- All command examples verified against actual implementation:
  - `taskforce run command ralph:init "description"` ✓
  - `taskforce run command ralph:step --output-format json` ✓
  - `.\scripts\ralph.ps1` ✓
- Terminology consistency verified (PRD, Iteration, Context Rotation, Gutter)
- Mermaid diagram included showing orchestrator flow
- Troubleshooting section addresses gutter detection and infinite loop prevention

### Change Log
- 2026-01-10: Implemented Ralph Loop Documentation & Examples story
  - Created comprehensive documentation in `docs/ralph.md`
  - Created quick-start guide in `examples/ralph_plugin/README.md`
  - Created example task and PRD files
  - Updated documentation index with Ralph Loop link
  - All acceptance criteria met and verified

### Status
Ready for Review
