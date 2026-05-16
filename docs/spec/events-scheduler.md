---
feature: events-scheduler
status: shipped
since: 2026-02-18
last_verified: 2026-05-16
owner: rudi77
adr: ADR-010
---

# Event Sources & Scheduler — External Triggers for the Agent

The framework's mechanism for letting external systems and timers drive the
agent. Event sources translate calendar entries, IMAP mail, file-system
changes, generic webhooks, and GitHub deliveries into `AgentEvent`s. The
scheduler fires cron, interval, and one-shot jobs into the same event stream.
Profile authors declare both via YAML; agent packages (e.g. butler) consume
the resulting events. Webhooks are exposed through a single generic HTTP
endpoint that hands the raw body to the matching source — provider-specific
signature verification stays inside the source.

## Capabilities (what the operator/profile-author can do)

- register a polling event source by short name (`calendar`, `imap_email`, `file_watcher`) from profile YAML
- register a push event source (`webhook`, `github`) and receive its payloads via the generic events endpoint
- schedule cron, interval, or one-shot jobs that publish `schedule.triggered` events
- attach a `ScheduleAction` (execute_mission / send_notification / publish_event / execute_workflow) to each job
- pause, resume, list, and remove jobs at runtime via the `SchedulerProtocol`
- persist scheduled jobs across restarts (file-backed by default)
- choose a per-job IANA timezone for cron expressions and naive one-shot datetimes
- pick a catch-up policy for runs missed during downtime (`coalesce: skip` or `run_once`)
- plug additional sources via the `taskforce.application.event_source_registry` (`register_event_source(name, factory)`)

## Invariants (what must always be true)

- A GitHub webhook with a mismatched HMAC signature is rejected with HTTP 401 before any agent code runs; the payload is dropped.
- A webhook addressed to an unregistered source name returns HTTP 404; a source that exists but cannot accept inbound HTTP (no `handle_inbound`) returns HTTP 400.
- A request body that is not valid JSON returns HTTP 415; the source is never invoked.
- A successful inbound delivery returns HTTP 202 with `{event_id, source, status: "accepted"}`.
- Scheduled jobs survive process restart: persisted state is restored on `SchedulerService.start()`.
- A one-shot job whose `last_fired_at` is already set is dropped at startup and never re-fires (crash-safe).
- `last_fired_at` and `last_run` are persisted **before** the job's action runs, so a crash mid-fire cannot duplicate it on restart.
- Cron expressions are evaluated in the job's IANA timezone; a non-existent local wall clock (DST forward gap) is skipped to the next valid match.
- Ambiguous local times on a DST backward jump resolve to a single UTC instant (`fold=0`), so each cron slot fires exactly once per day.
- Polling event sources never raise out of `_poll_loop`; per-cycle errors are logged and the loop continues at the next interval.
- Registering an event source name a second time without `replace=True` raises `ValueError` instead of silently shadowing the existing factory.

## API surface (the contract clients depend on)

- POST /api/v1/events/{source_name} → 202 with `{event_id, source, status}`
- POST /api/v1/events/{source_name} → 401 on signature verification failure
- POST /api/v1/events/{source_name} → 404 when no active source matches the name
- POST /api/v1/events/{source_name} → 400 when the source has no `handle_inbound` method
- POST /api/v1/events/{source_name} → 415 when the body is not valid JSON

The scheduler has no REST surface in the framework core; it is managed
in-process via `SchedulerProtocol` (and the agent-facing `schedule` tool).

## Configuration surface (the profile keys operators rely on)

Event sources (list under `event_sources:` in the profile YAML; each entry needs a `type` matching a registered factory):

- `type: calendar` — `poll_interval_minutes` (default 5), `lookahead_minutes` (60), `calendar_id` ("primary"), `credentials_file`
- `type: imap_email` — `host`, `port`, `username`, `password_env`, `mailbox` ("INBOX"), `mark_seen` (true), `poll_interval_minutes` (2)
- `type: file_watcher` — `paths: [<path>...]`, `recursive` (true), `change_types` (`created,modified,deleted`)
- `type: webhook` — `source_name` ("webhook"); no auth; intended for trusted-network use
- `type: github` — `secret` or `secret_env`, `require_signature` (true), `source_name` ("github")

Scheduler:

- `default_timezone: <IANA>` (default `"UTC"`) — applied to jobs without an explicit `timezone`
- `work_dir: <path>` (default `.taskforce`) — `scheduler/jobs/*.json` job-store location

Per-job fields on `ScheduleJob`:

- `schedule_type: cron | interval | one_shot`
- `expression: str` — 5-field cron (`"0 8 * * *"`), interval (`"15m"`, `"1h"`, `"30s"`, `"1d"`), or ISO datetime for one_shot
- `timezone: <IANA>` (default `"UTC"`)
- `coalesce: skip | run_once` (default `skip`)
- `enabled: bool`, `tenant_id`, `agent_id`

## Event stream contract (what callers of the event bus must handle)

`AgentEvent.event_type` values published by sources and the scheduler:

- `webhook.received` — generic and GitHub webhook deliveries; GitHub payloads carry normalized `{action, repo, actor, title, ...}` plus full `raw`
- `calendar.upcoming` — a not-yet-seen calendar item is within the lookahead window
- `email.received` — an unseen IMAP message was fetched
- `file.changed` — a watched path was created / modified / deleted
- `schedule.triggered` — a scheduled job fired; payload carries `{job_id, job_name, action, tenant_id, agent_id}`

The corresponding agent-facing stream-event names exposed to UI consumers
are `BUTLER_EVENT_RECEIVED` and `BUTLER_SCHEDULE_TRIGGERED` (in
`core/domain/enums.py::EventType`).

## Extension points

- `register_event_source(name, factory, *, replace=False)` in `taskforce.application.event_source_registry` — agent packages and plugins add new source types here; the daemon and the events route look them up by name.
- `WebhookCapableEventSource` protocol in `core/interfaces/event_source.py` — implement `handle_inbound(payload, headers)` to expose a source through `POST /api/v1/events/{source_name}`. Raise `ValueError` to trigger HTTP 401.
- `SchedulerProtocol` in `core/interfaces/scheduler.py` — alternative scheduler backends (Redis, APScheduler) can replace `SchedulerService` by satisfying this protocol.

## Tests (must exist and pass)

- spec("events-scheduler.webhook_invalid_signature_returns_401")
- spec("events-scheduler.webhook_unknown_source_returns_404")
- spec("events-scheduler.webhook_non_json_returns_415")
- spec("events-scheduler.webhook_non_capable_source_returns_400")
- spec("events-scheduler.scheduler_persisted_jobs_resume_on_start")
- spec("events-scheduler.one_shot_already_fired_skipped_on_restart")
- spec("events-scheduler.cron_respects_job_timezone")
- spec("events-scheduler.cron_skips_dst_forward_gap")
- spec("events-scheduler.coalesce_run_once_fires_single_catchup")
- spec("events-scheduler.coalesce_skip_drops_missed_runs")
- spec("events-scheduler.fire_persists_last_fired_at_before_action")
- spec("events-scheduler.polling_loop_continues_after_poll_error")
- spec("events-scheduler.register_duplicate_source_raises_without_replace")

## Known gaps

- **Polling event sources have no jitter** — every source ticks on a fixed `poll_interval_seconds`, so multiple sources with the same interval (e.g. five `calendar` accounts at 5 min) fire in lockstep and spike outbound API usage. Tracked in #352.
- **Heartbeat / checkpoint directories race on first write** — concurrent `start()` calls can both attempt `mkdir`, and the loser sees the directory missing for one tick. Tracked in #318.
- **Built-in cron parser supports only the 5-field grammar** with `*`, `,`, `-`, `/`. It rejects named months/weekdays (`MON`, `JAN`), `@`-aliases (`@daily`), `?`, and `L`/`#` qualifiers — surprising for operators used to Quartz/Vixie cron. No tracked issue yet.
- **Generic `webhook` source has no signature verification at all.** Anything reachable at `/api/v1/events/webhook` is trusted; the route must be firewalled or proxied behind auth.
- **GitHub HMAC verification has no replay protection.** A captured legitimate delivery can be replayed indefinitely (same gap as gateway, #285).
- **`FileWatcherEventSource` requires the configured paths to exist at start time.** Deleting and recreating the watched directory leaves the source attached to a stale inode on POSIX.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.
- **Scheduler has no REST surface in framework core.** Operators manage jobs only via the `schedule` agent tool or programmatically; there is no HTTP CRUD analogue to `/api/v1/events/{source_name}`.

## Cross-references

- adr: ADR-010 (Event-driven butler agent — primary design)
- related_spec: gateway.md (per-channel webhook endpoint; this spec covers the non-channel generic endpoint)
- related_spec: react-loop.md (agent execution triggered by `schedule.triggered` actions)
- docs: CLAUDE.md → "Event Sources" + "Butler Agent" sections
- commit: (introduced 2026-02-18, event-driven butler architecture)
