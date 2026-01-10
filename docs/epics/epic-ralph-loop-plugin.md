# Epic: Ralph Loop - Autonomous Plugin Enhancement

## Purpose
Implement the "Ralph Loop" technique as a pluggable extension to enable autonomous, multi-iteration development tasks while maintaining system state and learnings across fresh context windows.

## Epic Goal
Implement the Ralph Loop technique as a plugin consisting of specialized tools, slash commands, and a PowerShell orchestrator, minimizing changes to the core codebase.

## Epic Description

**Existing System Context:**
- Current relevant functionality: `Agent` (Lean Agent) with native tool calling and `PluginLoader` for external capabilities.
- Technology stack: Python 3.x, Typer (CLI), Rich (Console).
- Integration points: CLI `run` commands and the `examples/` plugin structure.

**Enhancement Details:**
- What's being added/changed: A structured JSON output for CLI, a `ralph_plugin` with PRD and Learnings management tools, and `/ralph:init`/`/ralph:step` slash commands.
- How it integrates: Through a PowerShell orchestrator (`ralph.ps1`) that coordinates `taskforce` executions with git commits.
- Success criteria: Successful completion of a complex autonomous build task with at least 3 context rotations.

## Stories

1. **Story 1: CLI Automation Bridge**
   Add `--output-format json` to `taskforce run` commands and ensure `ExecutionResult` is correctly serialized to enable machine parsing by the loop orchestrator.
2. **Story 2: Ralph Plugin & Commands**
   Develop the `ralph_plugin` (tools for `prd.json` and `progress.txt` management) and register the `/ralph:init` and `/ralph:step` slash commands.
3. **Story 4: Loop Orchestrator**
   Implement `scripts/ralph.ps1` to handle the `while` loop, git commits, token limit monitoring (rotation triggers), and final "Definition of Done" verification.

## Compatibility Requirements
- [x] Existing APIs remain unchanged (new options are additive).
- [x] Database schema changes are not required.
- [x] CLI UI remains consistent; JSON output is optional via flag.
- [x] Performance impact is zero when the plugin is not in use.

## Risk Mitigation
- **Primary Risk:** Infinite loops or high token consumption if "Gutter Detection" or "Success Criteria" fail.
- **Mitigation:** Implement a hard `max_iterations` cap (default 10-20) in the PowerShell script and require explicit checkbox-based completion in `prd.json`.
- **Rollback Plan:** Since it's a plugin and a script, deletion of the `examples/ralph_plugin` folder and `scripts/ralph.ps1` completely removes the feature.

## Definition of Done
- [x] CLI supports `--output-format json` with full execution metadata.
- [x] Ralph tools can read/update `prd.json` and append to `progress.txt`.
- [x] Slash commands correctly initialize and execute single steps.
- [x] PowerShell script successfully manages context rotation and git commits.
- [x] Documentation in `docs/ralph.md` is complete.
- [x] No regression in existing features.
