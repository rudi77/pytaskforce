---
feature: llm-router
status: shipped
since: 2026-02-22
last_verified: 2026-05-16
owner: rudi77
adr: ADR-012
---

# LLM Router — Dynamic Per-Call Model Selection

A transparent decorator around the LLM provider that picks a different model
for each call based on what the caller is doing. Planning strategies tag every
call with a **phase hint** (`planning`, `reasoning`, `acting`, `reflecting`,
`summarizing`); operators map those hints to model aliases via the `routing:`
block in `llm_config.yaml`. The router implements the same protocol as the
underlying provider, so agents and strategies are unchanged. When no rules are
configured, every hint falls back to the default model — fully backward
compatible.

## Capabilities (what the operator can do)

- map a phase hint to any model alias via `routing.rules` (e.g. send `planning` to a stronger model, `summarizing` to a cheap one)
- route by call context, not just hints: `has_tools`, `no_tools`, `message_count > N`
- order rules deliberately — first match wins, later rules ignored once one matches
- disable routing entirely (`routing.enabled: false`) and have all hints resolve to one default model
- override the default model per-router via `routing.default_model` (independent of `default_model` at the top of `llm_config.yaml`)
- pass an explicit known alias as the `model` parameter and bypass all routing rules

## Invariants (what must always be true)

- When the caller passes a model name that is a known alias in the delegate's `models` dict, the router passes it through unchanged — routing rules are not evaluated.
- Hint strings (`planning`, `reasoning`, `acting`, `reflecting`, `summarizing`) that do not match any alias are never sent to the underlying provider; the router resolves them to an alias first.
- When no routing rule matches and no known alias was supplied, the router uses `default_model`.
- Rule evaluation is deterministic and order-sensitive: the first rule whose condition matches wins, regardless of how many later rules could also match.
- A router with zero rules is a valid configuration: it transparently maps every hint to `default_model` while still passing known aliases through.
- The router implements the same `LLMProviderProtocol` as its delegate — wrapping is invisible to agents and planning strategies.
- A malformed condition (e.g. `message_count > abc`) is logged and skipped, never raised — one bad rule cannot break the router.
- `complete_stream` yields every chunk produced by the delegate in order; the router does not buffer, drop, or transform chunks.
- `generate()` does not evaluate routing rules — it only honors explicit known aliases or falls back to `default_model` (no `messages` / `tools` context to route on).

## Configuration surface (the `llm_config.yaml` keys operators rely on)

The router consumes the `routing:` block of `llm_config.yaml`:

- `routing.enabled: bool` (default `false`) — when false, the router is still built (so hints resolve), but no rules are loaded
- `routing.default_model: <alias>` — fallback alias when no rule matches (overrides the global `default_model` for routing purposes only)
- `routing.rules: list[{condition, model}]` — ordered list, first match wins. Supported conditions:
  - `hint:<name>` — matches when the caller passes `<name>` as the `model` parameter
  - `has_tools` — matches when the `tools` argument is a non-empty list
  - `no_tools` — matches when `tools` is None or an empty list
  - `message_count > N` — matches when the `messages` list has more than N items

Reserved hint names (must not be used as aliases in `models:`):
`planning`, `reasoning`, `acting`, `reflecting`, `summarizing`.

## Extension points

- `RoutingRule` dataclass in `taskforce.infrastructure.llm.llm_router` — a custom factory can build rule lists programmatically and instantiate `LLMRouter` directly (e.g. for tenant-scoped routing).
- `build_llm_router(delegate, routing_config, default_model)` — the documented constructor; any `LLMProviderProtocol` implementation can be the delegate, not only `LiteLLMService`.

## Tests (must exist and pass)

- spec("llm-router.known_alias_bypasses_rules")
- spec("llm-router.hint_routes_via_matching_rule")
- spec("llm-router.first_matching_rule_wins")
- spec("llm-router.unknown_hint_falls_back_to_default")
- spec("llm-router.empty_rules_pass_through_to_default")
- spec("llm-router.has_tools_matches_when_tools_present")
- spec("llm-router.no_tools_matches_when_tools_absent")
- spec("llm-router.message_count_threshold_respected")
- spec("llm-router.malformed_condition_is_ignored")
- spec("llm-router.complete_stream_preserves_chunk_order")
- spec("llm-router.generate_does_not_apply_routing_rules")
- spec("llm-router.alias_named_like_hint_takes_priority_over_rule")

## Known gaps

- **No `@pytest.mark.spec` markers exist yet** — coverage of the listed assertions lives in `tests/unit/infrastructure/test_llm_router.py` as plain pytest cases. Spec-check will flag every marker as "asserted but missing test" until the tests are tagged.
- **Multi-model fallback on content-filter timeout is not implemented.** The router picks one model per call; if that model trips a provider content filter, recovery (ADR-025) retries on the same alias rather than escalating to a different model. Tracked in #203.
- **`complete_json` fallback path picks an alias from `_select_model` without `tools`/`messages` context awareness.** When the delegate doesn't implement `complete_json`, the router synthesises a `messages` list from `prompt` + `system_prompt` and calls `complete` — context-based rules (`has_tools`, `message_count`) see this synthetic context, not the original caller's, which may produce surprising routing.
- **Complexity-override semantics (`complexity_override="simple"`) are undocumented in `llm_config.yaml`.** The `_apply_complexity_override` hook downgrades `main`/`powerful`/`powerful-1` to the `task_complexity.simple_model` alias, but the wiring (who sets `complexity_override`, when) is not part of the routing config schema.

## Cross-references

- adr: ADR-012 (Dynamic LLM Selection — this feature is Approach 3)
- related_spec: react-loop.md (strategies emit the phase hints this router consumes)
- related_spec: llm-service.md (the delegate that this router wraps)
- related_spec: content-filter-recovery.md (recovery path; see Known gap on multi-model fallback)
- docs: CLAUDE.md → "Dynamic LLM Routing" section
- commit: ee8cc46 (introduced 2026-02-22)
