---
feature: agent-daemon
status: shipped
since: 2026-05-13
last_verified: 2026-05-16
owner: rudi77
adr: ADR-027
---

# Agent Daemon — Long-Running Runtime for Any Profile

The generic, profile-driven daemon that keeps an agent alive between user
requests. It loads any installed profile (butler, coding_agent, rag_agent,
or a third-party plugin), wires together the scheduler, event sources, rule
engine, persistent agent queue, and the standing-goals heartbeat, then writes
periodic status files so operators can inspect liveness. A built-in supervisor
restarts the daemon on crash or stalled main loop, and several daemons may
run side-by-side on the same `work_dir` because every artifact is namespaced
by profile. This was butler-specific until ADR-027 promoted the lifecycle to
the framework; ADR-028 then reduced the butler package to YAML-only configs.

## Capabilities (what the operator/profile-author can do)

- start a long-running daemon for any installed profile via `taskforce daemon start --profile <name>`
- attach a role overlay (`--role <name>`) that replaces tools/sub-agents and sets the persona prompt
- inspect liveness via `taskforce daemon status --profile <name>` (reads `status.json`)
- write daemon logs to `<work_dir>/logs/<profile>.log` (override with `--log-name`)
- run multiple daemons concurrently for different profiles on the same `work_dir`
- get automatic restart on uncaught exceptions with exponential backoff (default cap 60 s)
- get automatic restart when the main-loop heartbeat stalls past the watchdog threshold (default 120 s)
- disable the supervisor for foreground/debug runs via `--no-supervisor`
- shut the daemon down gracefully via SIGINT / SIGTERM (POSIX) or SIGINT / SIGBREAK (Windows)
- seed event sources, scheduled jobs, trigger rules, and standing goals from profile YAML
- run with or without the persistent agent queue (default on; queue serialises mission execution)
- expose the daemon's queued/in-flight missions through `/api/v1/missions` when the API server runs in the same process

## Invariants (what must always be true)

- `status.json` lives at `<work_dir>/<profile>/status.json`, so two daemons with different `--profile` values never overwrite each other's status.
- A daemon stop unregisters every active event source from the API layer, so `POST /api/v1/events/{source_name}` returns 404 instead of dispatching to a halted source.
- A daemon stop drains the persistent agent queue before returning, and clears the API-side registration so `/api/v1/missions` reflects "no daemon".
- A `--role` overlay replaces the profile's `tools` and `sub_agents` wholesale, appends `event_sources`, `rules`, and `mcp_servers`, and sets `system_prompt` from the role's persona; infrastructure keys (`persistence`, `llm`, `scheduler`) stay from the base profile.
- A role lookup that finds no matching `<role>.agent.md` or `<role>.yaml` in any search directory is logged and the base profile keeps running unchanged (non-fatal).
- The proactive layer is started only when `proactive.enabled: true`; without that block the daemon is bit-for-bit reactive (pre-ADR-024 behaviour).
- Gateway, executor, persistent-agent, and proactive setup each fail soft — a single subsystem's import or wiring error is logged but does not abort daemon startup.
- The main loop refreshes `last_heartbeat` every status-write tick (30 s); a heartbeat older than `stall_threshold_seconds` raises `DaemonStalled` from the watchdog and triggers a supervised restart.
- The supervisor builds a fresh `AgentDaemon` instance for every restart cycle, so leaked tasks or half-initialised components from the previous iteration cannot survive into the next one.
- `KeyboardInterrupt`, `SystemExit`, and `CancelledError` from inside the supervised loop always skip the restart path and let the process exit cleanly.
- Backoff resets to its initial value (default 1 s) after a clean restart cycle, so a long-running daemon that later crashes does not inherit stale backoff state.
- Status writes are atomic — the file is written to `status.json.tmp` and renamed, so a concurrent `taskforce daemon status` never reads a half-written JSON document.

## Configuration surface (the profile keys / CLI flags operators rely on)

CLI surface (`taskforce daemon ...`):

- `start --profile <name>` *(required)* — profile to load; resolved through the same search path as `taskforce run mission`
- `start --role <name>` — role overlay; searched in `<agent-package-configs>/roles/` and `<work_dir>/roles/` (legacy `butler_roles/` also accepted)
- `start --work-dir <path>` (default `.taskforce`) — root for `status.json`, logs, rules, scheduler jobs, standing goals
- `start --no-supervisor` — run a single bare daemon, no watchdog / no auto-restart (foreground/debug use)
- `start --log-name <file>` (default `<profile>.log`) — log file under `<work_dir>/logs/`
- `status --profile <name>` — pretty-print `<work_dir>/<profile>/status.json`; exits 1 when the file is missing or malformed

Profile-YAML keys consumed by the daemon (in addition to the standard agent profile):

- `notifications.default_channel: str` (default `"telegram"`) — fallback channel for scheduled `send_notification` actions
- `notifications.default_recipient_id: str` (default `""`) — fallback recipient for the same
- `agent.llm_fallback: bool` (default `false`) — let the event router consult the LLM when no rule matches
- `event_sources: list` — see `events-scheduler.md`
- `rules: list` — trigger rules loaded into the `FileRuleEngine` at startup
- `proactive: { enabled, heartbeat_minutes, standing_goals }` — see `standing-goals.md`
- `request_queue.max_size: int` (default 100) and `request_queue.drain_timeout: float` (default 30 s) — `PersistentAgentService` queue tuning
- `auth.providers: dict` — provider configs handed to the shared `AuthManager`
- `role: <name>` — default role overlay when no `--role` CLI flag is passed

Role files live in `<agent-package-configs>/roles/<name>.agent.md` (preferred)
or `<name>.yaml` (legacy). A role overlay sets `persona_prompt` / `tools` /
`sub_agents` / `event_sources` / `rules` / `mcp_servers`; merge semantics are
spelled out under the invariants above.

Supervisor tuning (currently constructor-only, no profile keys):

- `watchdog_interval_seconds` (default 30) — how often the watchdog wakes
- `stall_threshold_seconds` (default 120) — heartbeat-age threshold for restart
- `initial_backoff_seconds` (default 1) / `max_backoff_seconds` (default 60) / `backoff_factor` (default 2)

## Extension points

- `taskforce.config_dirs` entry-point group — agent packages register their `configs/` directory so `--profile <name>` and `--role <name>` resolve transparently.
- `taskforce.application.event_source_registry.register_event_source` — agent packages add new event-source types the daemon can build from YAML.
- `AgentDaemon.touch_heartbeat()` — long-running internal tasks call this to keep the watchdog happy when they take longer than `stall_threshold_seconds`.
- `AgentDaemonSupervisor(daemon_factory=...)` — embedders pass any zero-arg callable returning a fresh daemon (used for testing and for embedding the daemon inside another long-running process).
- `set_persistent_agent_service`, `set_standing_goal_store`, `set_goal_evaluator`, `register_active_event_source` in `taskforce.api.dependencies` — the daemon publishes these so REST routes find the canonical in-process instances.

## Tests (must exist and pass)

- spec("agent-daemon.start_writes_status_under_profile_subdir")
- spec("agent-daemon.two_profiles_share_work_dir_without_collision")
- spec("agent-daemon.role_overlay_replaces_tools_and_sub_agents")
- spec("agent-daemon.role_overlay_appends_event_sources_and_rules")
- spec("agent-daemon.missing_role_logs_but_does_not_abort_start")
- spec("agent-daemon.stop_unregisters_active_event_sources")
- spec("agent-daemon.stop_drains_persistent_agent_queue")
- spec("agent-daemon.proactive_disabled_when_block_absent")
- spec("agent-daemon.supervisor_restarts_on_uncaught_exception")
- spec("agent-daemon.supervisor_restarts_on_stalled_heartbeat")
- spec("agent-daemon.supervisor_propagates_keyboardinterrupt_without_restart")
- spec("agent-daemon.supervisor_resets_backoff_after_clean_run")
- spec("agent-daemon.status_file_writes_are_atomic")
- spec("agent-daemon.signal_handlers_request_graceful_shutdown")

## Known gaps

- **No `@pytest.mark.spec` markers exist yet** — the Tests section asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.
- **No `taskforce daemon stop` subcommand.** Stopping requires Ctrl+C in the foreground session, sending SIGINT/SIGTERM (POSIX) or SIGBREAK (Windows) to the process, or killing it; there is no CLI-managed PID file or supervisor RPC.
- **No `taskforce daemon list` subcommand.** Operators discover running daemons by listing `<work_dir>/*/status.json` themselves; the CLI requires `--profile` for every call.
- **Supervisor tuning is constructor-only.** `watchdog_interval_seconds`, `stall_threshold_seconds`, and the backoff parameters cannot be set from profile YAML or CLI flags — only by embedders constructing `AgentDaemonSupervisor` directly.
- **`SIGTERM` is not handled on Windows.** Operators using Windows Service / NSSM stop semantics must rely on Ctrl+Break; `taskkill /F` bypasses Python signal handlers entirely.
- **Multiple daemons sharing a `work_dir` cooperate on filesystem layout but not on work.** Two daemons with the same `--profile` will both load the same rules, run the same scheduled jobs, and evaluate the same standing goals — there is no inter-process lock.
- **Auto-restart has no global crash cap.** A daemon that crashes on every start retries forever with capped backoff; there is no "give up after N consecutive crashes" circuit breaker.

## Cross-references

- adr: ADR-027 (Generic agent daemon — promotion from butler to framework)
- adr: ADR-028 (Butler as YAML-only package — the consequence of ADR-027)
- adr: ADR-010 (Event-driven butler agent — original design)
- adr: ADR-016 (Persistent agent architecture — `PersistentAgentService` + `RequestQueue`)
- adr: ADR-017 (Butler role specialization — origin of the role overlay)
- adr: ADR-024 (Standing goals — proactive heartbeat hosted by the daemon)
- related_spec: events-scheduler.md (event sources + scheduler the daemon hosts)
- related_spec: standing-goals.md (proactive heartbeat the daemon runs)
- related_spec: conversations.md (persistent agent + request queue the daemon owns)
- related_spec: gateway.md (communication gateway the daemon wires for outbound notifications)
- docs: CLAUDE.md → "Butler Agent (Optional Package)" + "Running the Butler" sections
- commit: da7e590 (Phase 2: promote agent daemon + role loader + generic tools to framework, 2026-05-13)
