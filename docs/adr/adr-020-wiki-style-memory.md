# ADR-020: Wiki-Style Long-Term Memory

**Status:** Accepted
**Date:** 2026-04-21
**Supersedes:** ADR-007 (Unified Memory Service), ADR-013 (Memory Consolidation), ADR-014 (Generative Dreaming)

## Context

The record-based long-term memory introduced in ADR-007 (and extended by
ADR-013 and ADR-014) treated memory as an *episodic* event stream: every
session produced new records, consolidation jobs distilled them into
further `consolidated` records, and the dream engine created even more.
There was no mechanism for deduplicating against existing records or
merging knowledge about the same topic.

Real-world usage confirmed the failure mode. On a single user's wiki
store the file had grown to **27 MB / 2 814 records** (99.2 % of kind
`consolidated`) with an average of **259 tags per record** and a few
records carrying up to **940 bidirectional associations**. Near-duplicate
records covered the same topic five or more times with slightly
different phrasings; tag-vocabulary synonyms (`fallback`,
`fallback-route`, `graceful-degradation`, `recovery`, `failover`)
accumulated without curation; narrative sentences were used as tags.

The drivers of the growth were three services — `ConsolidationService`
(triggered every 50 requests / 60 min), `DreamService` (triggered on
idle cycles) and `LearningService` (session-end extraction) — combined
with `_discover_associations`, which linked records by tag overlap.

## Decision

Replace the record-based store with a **wiki-style memory**: a
directory of markdown files, one per topic, which the agent curates
incrementally. Adopt the pattern described in
<https://github.com/rudii/llm-wiki> (the "LLM Wiki" idea): raw sources
are immutable, the wiki is an LLM-owned set of interlinked markdown
pages, and a small schema (this ADR + the butler prompt) tells the
agent how to maintain it.

Concretely:

* Memory is stored as individual `.md` files under
  `.taskforce/memory/wiki/<kind>/<slug>.md`, where `<kind>` is one of
  `entities` (people/companies/contacts), `preferences` (formats,
  workflows) or `concepts` (process rules, patterns). An `index.md`
  catalogue and an append-only `log.md` live at the wiki root.
* Each page has YAML frontmatter (`title`, `tags`, `created_at`,
  `updated_at`) and a markdown body with `##` sections. Cross-links
  between pages use `[[kind/slug]]` syntax.
* The `memory` tool is replaced by the `wiki` tool whose actions
  (`list_pages`, `read_page`, `search`, `write_page`, `update_page`,
  `delete_page`, `log`) map directly onto these pages.
* There is no tag graph, no associations, no strength/decay, no
  emotional valence, no importance floor. Relevance comes from
  keyword-based search over page content + title, plus the agent's
  explicit choice of which page to open.
* `ConsolidationService`, `DreamService`, `LearningService`,
  `_discover_associations` and the record-based `MemoryStoreProtocol`
  are deleted. Their role as "refine memory in the background" is
  delegated to the agent itself at save-time (`update_page` instead
  of creating new records).
* A manual `taskforce wiki lint` command reports orphans, duplicate
  titles and broken wiki-links. Running it is the user's choice — it
  replaces the previous automatic consolidation cycles.
* Existing `memory.md` is archived to `memory.md.archive-YYYY-MM-DD`
  and not loaded. Users start with an empty wiki.

## Consequences

### Positive

* Memory is now a compounding, human-readable artifact instead of an
  opaque record stream. The user can open the wiki in Obsidian or any
  markdown viewer and see exactly what the agent knows.
* Writes stop being append-only: the agent updates the matching page
  in place, so the same topic never creates duplicate records.
* The framework loses three services (consolidation, dream, learning)
  and four protocols (`MemoryStoreProtocol`, `ConsolidationProtocol`,
  `DreamEngineProtocol`, `LearningStrategyProtocol`). The agent still
  saves proactively, but the responsibility for *where* something is
  saved now lives in the agent prompt, not in a background pipeline.
* Wiki growth is bounded by the number of distinct topics the user
  discusses, not by the number of sessions.

### Negative / Trade-offs

* Starting with an empty wiki means losing the ~23 curated
  preferences/facts that were in the old store (the 27 MB was almost
  entirely consolidated noise; the real content was tiny). This is
  acceptable: we accepted history loss in exchange for a clean
  architecture.
* Search is keyword-based (BM25-like) rather than embedding-based in
  v1. Acceptable for small wikis (~hundreds of pages). Embeddings can
  be bolted on later (see "Future work").
* No cross-session analytics or automatic insight generation. If the
  user wants cross-session summaries they can ask the agent
  explicitly; the agent will search the wiki and answer in-chat.

### Migration

* No automatic migration. `memory.md` is renamed to
  `memory.md.archive-2026-04-21`. Users who want old preferences
  restored can copy them manually into the new wiki pages.
* The `memory` short-name in the tool registry is replaced by `wiki`.
  All profiles under `src/taskforce/configs/`, `agents/*/configs/`
  and `examples/*/configs/` are updated. External profiles that still
  reference `memory` will fail to resolve their tool list at build
  time.

## Future Work

* Optional embedding-backed search via an embeddings provider wired
  into `FileWikiStore`. Deferred until a wiki actually grows past the
  point where keyword search is insufficient.
* Automatic `wiki lint` scheduling through the existing scheduler
  (currently manual only).
* Image/attachment handling in wiki pages (currently text-only).

## References

* Implementation branch: `wiki-memory`
* Superseded ADRs: [ADR-007](adr-007-unified-memory-service.md),
  [ADR-013](adr-013-memory-consolidation.md),
  [ADR-014](adr-014-generative-dreaming.md)
* Related pattern: LLM Wiki (personal knowledge base maintained by an
  agent, with `index.md` + `log.md` + per-topic pages).
