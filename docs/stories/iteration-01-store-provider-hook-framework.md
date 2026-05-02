# Iteration 1 (Framework) — Store-Provider Hook in `AgentFactory`

**Status:** In Review (branch ready for PR)
**Repo:** `pytaskforce`
**Branch:** `feat/iter-01-store-provider-hook`
**Effort:** 2-3 days
**Roadmap:** [`docs/enterprise-saas-roadmap.md`](../enterprise-saas-roadmap.md)
**Companion story:** `taskforce-enterprise/docs/stories/iteration-01-tenant-scoped-stores-plugin.md`
**ADR:** [ADR-022 §3 — Late-Bound Store Providers in `AgentFactory`](../adr/adr-022-multi-tenant-enterprise-runtime.md)

---

## Goal

Make `AgentFactory` accept *late-bound* store providers, so an external
plugin (the eventual `taskforce-enterprise` extension) can decide which
store instance to return *per agent build*. The framework itself learns
nothing new — it just stops eagerly capturing store singletons in fields
and starts holding callables that return them.

This is the **only** framework change required for multi-tenancy. All
tenant logic lives in the enterprise plugin and is delivered in the
companion story.

## Non-Goals (explicit)

- **No `tenant`/`tenant_id` vocabulary anywhere in `src/taskforce/`.**
  Reviewers must reject any code in this PR that mentions tenants. The
  framework is unaware of the concept.
- No protocol changes. `ConversationManagerProtocol`, `StateManagerProtocol`,
  `AgentRegistry`, `WikiStoreProtocol` etc. are untouched.
- No file-layout changes. `${WORK_DIR}/conversations/...` stays where it is.
- No new persistence interface. Existing protocols are reused as-is.
- No migration logic.
- No authentication, no JWT, no users.

## Acceptance Criteria

1. **Bit-for-bit behavioural identity in single-tenant mode.** All
   existing tests pass without modification. Single-tenant CLI runs
   (`taskforce run mission "..."`, `taskforce chat`, `taskforce butler
   start`) produce identical filesystem output as before.
2. **Provider hook works.** A new test installs a custom provider that
   returns a different `ConversationManagerProtocol` instance per call
   and asserts the factory uses the latest provider when building an
   agent.
3. **No tenant vocabulary.** A `grep` for `tenant` over the diff in
   `src/taskforce/` returns nothing other than possibly an ADR
   reference comment.
4. **Lint, format, type-check clean.** `ruff`, `black`, `mypy` green
   for touched files.
5. **Docs updated.** `CLAUDE.md` "Application" section gets a
   one-paragraph note describing the new hook. ADR-022 gets a status
   note: "Iteration 1 (framework hook) merged in PR #…".

---

## Design

### Today: stores held as instance fields

```python
class AgentFactory:
    def __init__(self) -> None:
        ...
        self._conversation_store: ConversationManagerProtocol = FileConversationStore(...)
        self._state_manager: StateManagerProtocol = FileStateManager(...)
        self._agent_registry: AgentRegistry = AgentRegistry(...)
        ...

    async def create_agent(self, ...) -> Agent:
        ...
        agent = Agent(
            conversation_store=self._conversation_store,
            state_manager=self._state_manager,
            ...
        )
```

### After: stores resolved through provider callables

```python
class AgentFactory:
    def __init__(self) -> None:
        ...
        # Default providers wrap a singleton — semantically identical to today.
        default_conv = FileConversationStore(...)
        default_state = FileStateManager(...)
        default_registry = AgentRegistry(...)

        self._conversation_store_provider: Callable[[], ConversationManagerProtocol] = lambda: default_conv
        self._state_manager_provider: Callable[[], StateManagerProtocol] = lambda: default_state
        self._agent_registry_provider: Callable[[], AgentRegistry] = lambda: default_registry
        ...

    # New extension API
    def set_conversation_store_provider(
        self,
        provider: Callable[[], ConversationManagerProtocol],
    ) -> None: ...

    def set_state_manager_provider(
        self,
        provider: Callable[[], StateManagerProtocol],
    ) -> None: ...

    def set_agent_registry_provider(
        self,
        provider: Callable[[], AgentRegistry],
    ) -> None: ...

    async def create_agent(self, ...) -> Agent:
        agent = Agent(
            conversation_store=self._conversation_store_provider(),
            state_manager=self._state_manager_provider(),
            ...
        )
```

### One-line addendum: `AgentRegistry.custom_dir_subpath`

`AgentRegistry` today hard-codes `self.custom_dir = self.config_dir / "custom"`.
The plugin wants per-tenant subdirectories like `custom/${tenant_id}/`. To
keep the plugin from forking `AgentRegistry`, this iteration adds **one
optional kwarg** to `AgentRegistry.__init__`:

```python
def __init__(
    self,
    config_dir: Path | str | None = None,
    base_path: Path | None = None,
    custom_dir_subpath: str = "custom",   # NEW
) -> None:
    ...
    self.custom_dir = self.config_dir / custom_dir_subpath
```

Default value preserves current behaviour exactly. No other call site
in the framework needs to pass it. This is the only change beyond the
provider hook itself.

### Which stores get the hook?

Iteration 1 only adds providers for the **three stores that the enterprise
plugin needs in Iteration 1 + 3**:

| Store | Why now |
|---|---|
| `AgentRegistry` (`build_agent_registry`) | Beta journey: separate custom-agent set per tenant |
| `StateManagerProtocol` (currently `FileStateManager`, via `build_state_manager`) | Required so the agent's session state lands in the per-tenant directory |
| Gateway components (`build_gateway_components`) — includes the conversation store and recipient registry | Beta journey: separate conversations per tenant |

Other stores (`WikiStoreProtocol`, `MemoryStoreProtocol`, the scheduler
job store, the heartbeat store, etc.) keep their current direct-field
wiring. Their providers will be added in later iterations as needed
(Iter 12 for memory, including the wiki store). This is deliberate —
adding all 12 hooks at once is YAGNI; we add one per iteration that
needs it. Wiki store specifically also has a non-trivial bypass at
`application/factory.py` which constructs `FileWikiStore` directly with
a profile-resolved store dir; routing that through the override
requires either a second builder method or a signature change, both of
which are out of scope here.

### Known coverage gap (acceptable for Iter 1)

`api/cli/simple_chat.py` constructs gateway components directly via
`gateway_registry.build_gateway_components(...)` rather than going through
`InfrastructureBuilder`. This means the Telegram-polling chat path
inside `simple_chat` will not see plugin-installed overrides. This is
acceptable for Iter 1 because:

- `simple_chat` is the single-tenant interactive CLI, not the API
  server which the enterprise plugin actually targets.
- The plugin's Iter 3 web-chat path goes through
  `api/dependencies.py::get_gateway_components`, which routes through
  `InfrastructureBuilder` and thus picks up the override correctly.

If/when an enterprise deployment needs `simple_chat` to be tenant-aware
(e.g. for multi-user CLI testing) the call site can be migrated then.

### Plugin extension point — already exists

The enterprise plugin already declares a `taskforce.factory_extensions.enterprise`
entry point. Iter 1 simply gives that entry point three new things to do:

```python
# Plugin-side, NOT in this iteration's framework PR
def factory_extension(factory: AgentFactory, config: dict) -> None:
    tenant_factory = TenantScopedStoreFactory(...)
    factory.set_conversation_store_provider(
        lambda: tenant_factory.conversation_store_for_current_tenant()
    )
    factory.set_agent_registry_provider(
        lambda: tenant_factory.agent_registry_for_current_tenant()
    )
    factory.set_state_manager_provider(
        lambda: tenant_factory.state_manager_for_current_tenant()
    )
```

The framework PR exposes the three setter methods. The plugin PR (separate
repo, separate branch, see companion story) implements the actual logic.

### Why callables, not objects-with-`get_for_request()`?

Two reasons:
1. **Zero-overhead in single-tenant mode.** A `lambda: singleton` is
   one indirection, no allocations, no protocol dispatch.
2. **Plugin-author ergonomics.** The plugin can pick whatever
   internal API it likes (ContextVars, async-task-locals, custom
   resolvers). The framework doesn't dictate.

---

## Files Touched

| File                                               | Change      |
|----------------------------------------------------|-------------|
| `src/taskforce/application/factory.py`             | modify      |
| `src/taskforce/application/factory_extensions.py` (new, optional) | add — only if we want a typed extension contract; otherwise the three setters on `AgentFactory` are enough |
| `tests/unit/application/test_factory_providers.py` (new) | add       |
| `CLAUDE.md`                                        | modify (one paragraph) |
| `docs/adr/adr-022-multi-tenant-enterprise-runtime.md` | modify (status note) |
| `docs/enterprise-saas-roadmap.md`                  | modify (status → Done with PR link) |

**Estimated diff size:** ~150-250 lines including tests. Tiny on
purpose — the enterprise plugin does the heavy lifting.

## Test Plan

### New tests

1. `test_factory_providers.py`:
   - `test_default_provider_returns_same_instance`: calling `create_agent`
     twice yields agents whose stores are the same identity.
   - `test_custom_provider_invoked_per_build`: install a provider that
     returns a fresh stub each call; assert two agents have different
     store instances.
   - `test_provider_swap_at_runtime`: change the provider between two
     `create_agent` calls; assert the second agent uses the new provider.
   - `test_default_behaviour_unchanged`: assert the file paths the
     default provider's store writes to are identical to today's
     (regression guard).

### Existing tests

All existing factory and infrastructure tests must pass without change.

### Manual smoke

Run `taskforce run mission "say hello"` against an existing
`.taskforce/` directory. Diff the resulting filesystem against a
pre-iter-1 run — must be identical.

---

## Risks & Mitigations

| Risk                                                          | Mitigation                                                                          |
|---------------------------------------------------------------|-------------------------------------------------------------------------------------|
| Hidden call sites bypass the provider and grab the default singleton directly | Audit `factory.py` and surrounding modules for direct field access (`self._conversation_store`); replace with provider call. PR description must list every touched call site. |
| Future iterations want the hook for stores we didn't lift     | Adding a new provider later is mechanically the same change. We document the pattern in `CLAUDE.md` so future iterations can repeat it. |
| `ruff` / `mypy` complain about `Callable[[], Protocol]` typing | Use `Callable[[], <ConcreteProtocol>]` form, mypy supports it. If not, fall back to a tiny `class Provider(Protocol): def __call__(self) -> ...: ...`. |

---

## Workflow

1. `git switch -c feat/iter-01-store-provider-hook` from `main`.
2. Refactor `AgentFactory` to use providers; keep behaviour identical.
3. Add the three `set_*_provider` methods.
4. Add new test file. Run full test suite locally.
5. `ruff`, `black`, `mypy` clean.
6. Grep the diff for `tenant` — must return zero hits.
7. Update `CLAUDE.md`, ADR-022, roadmap.
8. Open PR titled `feat: store-provider hook in AgentFactory (iter 1, framework)`.
9. PR description lists each Acceptance Criterion and ticks it.
10. Run `/ultrareview` on the PR.
11. After merge: tell the companion plugin PR to depend on `main`,
    then merge that next.

## Done Definition

- All Acceptance Criteria checked.
- PR merged to `main` in `pytaskforce`.
- Roadmap row for Iter 1 marks framework PR as Done with link.
- Companion plugin story moves to `In Progress`.
