# Implement Agent Factory with Profiles

**Status**: Ready for Review

## Story Description

As a Developer
I want to update the AgentFactory to support "Profiles" (Kernel + Specialist)
So that I can dynamically create agents with specific capabilities (Coding, RAG, etc.) while maintaining a consistent autonomous baseline behavior.

## Context
We are moving to a layered architecture where every agent shares a common "Kernel" (autonomy instructions) but has different "Profiles" (specialist tools and instructions). The `AgentFactory` needs to assemble these pieces dynamically.

## Acceptance Criteria

- [x] **Prompts Definitions**: Constants for `GENERAL_AUTONOMOUS_KERNEL_PROMPT` and `CODING_SPECIALIST_PROMPT` (and potentially `RAG_SPECIALIST_PROMPT`) are defined in a prompts module.
- [x] **Factory Interface Update**: `AgentFactory.create_agent` accepts an optional `specialist` argument (default: "generic").
- [x] **Prompt Assembly**: The factory concatenates the Kernel prompt with the requested Profile prompt via `_assemble_system_prompt()`.
- [x] **Tool Injection**: The factory selects the appropriate toolset based on the profile via `_create_specialist_tools()`:
    - **Coding**: `FileReadTool`, `FileWriteTool`, `PowerShellTool`, `AskUserTool`.
    - **RAG**: `SemanticSearchTool`, `ListDocumentsTool`, `GetDocumentTool`, `AskUserTool`.
- [x] **Instantiation**: The `Agent` is initialized with the assembled prompt and toolset.

## Technical Notes

- **File**: `src/taskforce/application/factory.py`
- **File**: `src/taskforce/core/prompts/autonomous_prompts.py` (New file for the large prompt constants)
- **Design**:
  ```python
  system_prompt = GENERAL_AUTONOMOUS_KERNEL_PROMPT
  if profile == "coding":
      system_prompt += "\n\n" + CODING_SPECIALIST_PROMPT
      tools = [...]
  ```

## Dependencies
- Depends on Story 1 (Autonomous Kernel Infrastructure) for the agent to actually *use* the kernel instructions (looping behavior).

---

## Dev Agent Record

### Agent Model Used
Claude Opus 4.5

### File List
| File | Status |
|------|--------|
| `src/taskforce/core/prompts/autonomous_prompts.py` | Created |
| `src/taskforce/core/prompts/__init__.py` | Modified |
| `src/taskforce/application/factory.py` | Modified |
| `tests/unit/test_factory.py` | Modified |
| `configs/coding_dev.yaml` | Created |
| `configs/dev.yaml` | Modified |
| `configs/rag_dev.yaml` | Modified |
| `configs/prod.yaml` | Modified |
| `configs/staging.yaml` | Modified |

### Change Log
- Created `autonomous_prompts.py` with `GENERAL_AUTONOMOUS_KERNEL_PROMPT`, `CODING_SPECIALIST_PROMPT`, and `RAG_SPECIALIST_PROMPT`
- Added `specialist` parameter to `AgentFactory.create_agent()` method
- Added `_assemble_system_prompt()` method for Kernel + Specialist prompt composition
- Added `_create_specialist_tools()` method for profile-specific tool injection
- Updated prompts `__init__.py` to export new prompt constants
- **Config-based specialist loading**: Factory now reads `specialist` from YAML config if not provided as parameter
- **Option B: Config tools override specialist defaults**:
  - If config has `tools:` defined → use those tools (regardless of specialist)
  - If config has NO `tools:` → use specialist default tools
  - The `specialist` field always determines the system prompt
- Created `coding_dev.yaml` config with `specialist: coding` and explicit tools
- Updated all config profiles to include `specialist` field (generic/coding/rag)
- Added 13 new tests in `TestSpecialistProfiles` class covering:
  - Prompt assembly for generic/coding/rag profiles
  - Tool creation for coding/rag profiles
  - Agent creation from specialist configs
  - Config tools override specialist defaults
  - Specialist parameter overrides config for prompt
  - Validation of invalid profiles

### Completion Notes
- All 13 specialist profile tests pass
- The `specialist` parameter was used instead of `profile` to avoid confusion with the existing `profile` parameter (which controls dev/staging/prod config)
- Agents can now be created simply via `factory.create_agent(profile="coding_dev")` to get a coding specialist
- **Tool Override Logic**: Config tools take precedence over specialist defaults, allowing full customization per config while maintaining specialist prompts
- Pre-existing test failures in the test suite were not addressed as they are unrelated to this story (deprecated `_create_rag_tools` method tests)

### Debug Log References
N/A

