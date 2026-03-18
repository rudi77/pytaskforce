# Phase 3: Session-Deprecation — Implementation Plan

## Scope (from ADR-016)

1. Session-Endpoints als Deprecated markieren
2. CLI Default wechselt auf Persistent-Modus
3. Session-Code bleibt für Sub-Agent-interne Nutzung

---

## Step 1: Deprecate REST Session Endpoints

**File:** `src/taskforce/api/routes/sessions.py`

- Add `deprecated=True` to all 3 route decorators (OpenAPI will show them as deprecated)
- Add `Deprecation` + `Sunset` response headers
- Log a `structlog` warning on each call pointing to conversation endpoints

No deletion — endpoints stay functional.

## Step 2: Deprecate `session_id` in Execution API

**File:** `src/taskforce/api/routes/execution.py`

- Update `session_id` Field description to include deprecation notice, recommend `conversation_id`
- Log warning when `session_id` is provided without `conversation_id`

## Step 3: Deprecate CLI `sessions` Command

**File:** `src/taskforce/api/cli/commands/sessions.py`

- Add deprecation warning (`console.print`) at start of `list` and `show` commands
- Point users to `taskforce conversations` as replacement

## Step 4: CLI Chat Default to Persistent Mode

**File:** `src/taskforce/api/cli/simple_chat.py`

Currently: `session_id` + `StateManager` is primary, `ConversationManager` is optional mirror.
Change: `ConversationManager` becomes primary, `session_id` kept as internal plumbing.

- On startup: always initialize `ConversationManager` (not just when explicitly wired)
- History read/write goes through `ConversationManager.get_messages()` / `append_message()`
- Session state still saved for backward compat but conversation is the source of truth
- Status line shows conversation_id instead of session_id

**File:** `src/taskforce/api/cli/commands/chat.py`

- Wire `ConversationManager` by default when launching chat

## Step 5: Add Conversation REST Endpoints

**File:** `src/taskforce/api/routes/conversations.py` (NEW)

REST counterpart to the conversations CLI (replacement for sessions endpoints):
- `GET /api/v1/conversations` — list active (query param `archived=true` for archived)
- `GET /api/v1/conversations/{conversation_id}/messages` — get messages
- `POST /api/v1/conversations/{conversation_id}/archive` — archive
- `POST /api/v1/conversations` — create new conversation (params: channel, sender_id)

Register in `server.py` with `tags=["conversations"]`.

## Step 6: Update Documentation

- `docs/cli.md` — deprecation notice on sessions, add conversations commands
- `docs/api.md` — deprecation notice on session endpoints, document conversation endpoints

## Step 7: Tests

- Verify deprecation headers on session endpoints
- Tests for new conversation REST endpoints
- Verify CLI chat uses ConversationManager by default
- Full regression suite
