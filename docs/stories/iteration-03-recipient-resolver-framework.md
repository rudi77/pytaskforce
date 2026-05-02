# Iteration 3 (Framework) — `RecipientResolverProtocol` for Communication Gateway

**Status:** Planned (depends on Iter 1 framework merge)
**Repo:** `pytaskforce`
**Branch:** `feat/iter-03-recipient-resolver`
**Effort:** 1-2 days
**Roadmap:** [`docs/enterprise-saas-roadmap.md`](../enterprise-saas-roadmap.md)
**Companion story:** `taskforce-enterprise/docs/stories/iteration-03-web-chat-plugin.md`
**ADR:** [ADR-022 §4 — Tenant-aware Communication Gateway](../adr/adr-022-multi-tenant-enterprise-runtime.md)

---

## Goal

Add a tiny extension point to the `CommunicationGateway` so a plugin
can resolve a channel-specific identity (web JWT, Telegram user_id,
Teams oid) into a logical recipient that the gateway routes to a
specific agent.

The framework gets one new optional protocol and one constructor
kwarg on the gateway. **No tenant vocabulary.** Whether the resolver
returns a tenant-scoped or global recipient is the plugin's concern.

## Non-Goals

- No `tenant_id` on the protocol. The recipient identifier is opaque
  to the framework.
- No JWT validation in the framework — `AuthMiddleware` (plugin) does
  that already; the gateway only sees the result.
- No `@agent_name` parsing. Iter 3 ships single-default-agent routing;
  multi-agent dispatch is post-Beta.
- No web UI here — the UI lives in the enterprise plugin or a
  separate UI repo.

## Acceptance Criteria

1. **`RecipientResolverProtocol`** lives in
   `core/interfaces/gateway.py` next to the existing gateway protocols.
   Single method: `resolve(channel: str, channel_identity: dict[str, Any]) -> RecipientInfo | None`.
2. **`CommunicationGateway` accepts an optional resolver**, defaults to
   a pass-through that treats `channel_identity["sender_id"]` as the
   recipient. Behaviour for existing callers is unchanged.
3. **A new `default_agent_id` field on the resolved recipient** lets
   the gateway route to a per-recipient default agent without the
   gateway needing to know how that defaults gets set.
4. **Framework tests pass unchanged.** New tests cover the resolver
   contract and the pass-through default.
5. **No tenant vocabulary** — same `grep` rule as Iter 1.

## Design (sketch)

```python
# core/interfaces/gateway.py — additions

@dataclass(frozen=True)
class RecipientInfo:
    """Resolved recipient for an inbound message.

    The framework treats `recipient_id` opaquely. The plugin decides
    its meaning (tenant-scoped user id, global user id, anonymous
    session, ...).
    """
    recipient_id: str
    default_agent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


class RecipientResolverProtocol(Protocol):
    async def resolve(
        self,
        channel: str,
        channel_identity: dict[str, Any],
    ) -> RecipientInfo | None:
        """Resolve a channel-specific identity to a logical recipient.

        Returns None if the identity cannot be mapped (gateway responds
        with an audited deny)."""
        ...
```

Default pass-through implementation:

```python
class _PassthroughRecipientResolver:
    async def resolve(self, channel, channel_identity):
        sender_id = channel_identity.get("sender_id")
        if sender_id is None:
            return None
        return RecipientInfo(recipient_id=sender_id)
```

`CommunicationGateway.__init__` gains `resolver: RecipientResolverProtocol | None = None`
defaulting to the pass-through. Inbound message processing in the
gateway calls the resolver before deciding which agent to route to;
the existing routing logic is unchanged otherwise.

## Files Touched

| File                                                                | Change |
|---------------------------------------------------------------------|--------|
| `src/taskforce/core/interfaces/gateway.py`                          | modify |
| `src/taskforce/application/gateway.py`                              | modify (constructor + one call site) |
| `tests/unit/application/test_gateway_recipient_resolver.py` (new)   | add    |
| `CLAUDE.md`                                                         | one paragraph |
| `docs/adr/adr-022-multi-tenant-enterprise-runtime.md`               | status note |

**Estimated diff size:** ~150-200 lines.

## Test Plan

- Default pass-through preserves existing behaviour.
- A custom resolver returning `RecipientInfo(recipient_id="...", default_agent_id="acc")`
  causes the gateway to route to agent `acc`.
- Resolver returning `None` produces an audited deny.

## Workflow

1. `git switch -c feat/iter-03-recipient-resolver`.
2. Add protocol + dataclass.
3. Wire into `CommunicationGateway`.
4. Add tests.
5. Lint/format/type-check.
6. Update `CLAUDE.md`, ADR-022, roadmap.
7. PR + `/ultrareview` + merge.

## Done Definition

- Acceptance Criteria checked.
- PR merged.
- Roadmap row for Iter 3 framework set to Done.
- Companion plugin PR can begin review.
