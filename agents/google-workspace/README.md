# taskforce-google-workspace

Google Workspace tools for the taskforce framework — Gmail, Google
Drive, Google Calendar. Each tool registers via the
``taskforce.tools`` entry-point group (see
[ADR-026](../../docs/adr/adr-026-entry-point-plugin-discovery.md)) so
any agent profile can pull them in by short name.

## Installation

```bash
uv pip install taskforce-google-workspace
# or, from this checkout:
uv sync   # adds agents/google-workspace to the workspace
```

The package pulls in ``google-api-python-client`` and the matching
``google-auth*`` family. First-time use also needs OAuth credentials
on disk at ``~/.taskforce/google_token.json`` (run the
``authenticate`` tool from a chat session, or use
``scripts/google_auth.py``).

## Tools

| Short name | Class | Notes |
|------------|-------|-------|
| ``gmail`` | ``GmailTool`` | List / read / send / draft. Supports ``since_last_check`` for poll-style schedulers. Honours the framework's per-(tenant, user) state-dir override for ``gmail_seen.json``. |
| ``google_drive`` | ``GoogleDriveTool`` | List / get / download / upload / update / delete / create_folder / search. |
| ``calendar`` | ``CalendarTool`` | List events, list calendars, create, update, delete events. |

The provider-agnostic ``authenticate`` tool stayed in the framework
(``taskforce.infrastructure.tools.native.auth_tool``) — it kicks off
OAuth flows configured against any provider via the ``AuthManager``,
not specifically Google.

## Usage from a profile

```yaml
# agents/<your-agent>/configs/<profile>.agent.md
tools:
  - gmail
  - calendar
  - google_drive
  - authenticate
```

## Status

- **Phase 3** (board: #246) extracted these tools from the Butler
  package — see ``~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md``.
- Drive does not yet accept an ``auth_manager`` constructor argument
  (Gmail and Calendar do). Adding it is a follow-up item — currently
  Drive uses the legacy file-based token only.
