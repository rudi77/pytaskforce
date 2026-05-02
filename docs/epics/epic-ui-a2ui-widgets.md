# Epic: A2UI-style Interactive Widgets in Chat

**Status:** Planned
**Priorität:** Mittel
**Aufwand:** M (Medium)
**Vision:** Aus dem Chat soll ein interaktives Surface werden — Bilder, Listen,
Tabellen und Buttons rendern, Button-Events fließen wieder zurück an den Agent.
Anlehnung an [a2ui.org](https://a2ui.org/).

---

## 1. Ausgangslage (Stand 2026-05-02)

Die UI hat bereits den Render-Scaffold:

- `ui/src/features/chat/widgets/types.ts` — typisierte `WidgetSpec` (image,
  list, table, buttons, card), `MessagePart`, `WidgetEvent`, Handler-Signatur.
- `ui/src/features/chat/widgets/WidgetRenderer.tsx` — rendert jede Widget-Art;
  Buttons feuern `onEvent({kind:"button.pressed", actionId, widgetId, messageId})`.
- `ui/src/features/chat/MessageContent.tsx` — kombiniert Markdown-Text und
  Widgets innerhalb einer Nachricht.
- `ChatMessage.parts?: MessagePart[]` als optionales Feld in `api/queries.ts`.

**Was fehlt:** das Backend liefert noch keine Widgets, die UI postet noch keine
Widget-Events zurück, und es gibt kein verbindliches Protokoll auf der ACP-/REST-
Ebene.

---

## 2. Zielbild

1. Agent kann beliebige A2UI-Widgets als Teil einer Antwort streamen.
2. UI rendert sie inline neben dem Markdown-Text.
3. Klick auf einen Button (oder Auswahl in einem List/Form-Widget) erzeugt ein
   strukturiertes Event, das als neue Nachricht (oder dedizierter Widget-Event)
   wieder im Conversation-Stream landet.
4. Der Agent sieht das Event als Tool-Result-äquivalente Observation und kann
   darauf weiter planen.

---

## 3. Story-Übersicht

| # | Titel | Schicht | Aufwand |
|---|-------|---------|---------|
| 1 | A2UI-Schema im Backend modellieren | `core/domain/` | S |
| 2 | Stream-Event `widget` definieren | `application/`, SSE | S |
| 3 | Widget-Emit-API für Tools/Skills | `infrastructure/tools/` | M |
| 4 | UI: Stream-Reader für `widget`-Events | `useChatStream.ts` | S |
| 5 | UI: Widget-Events zurück an den Agent posten | API + Hook | M |
| 6 | Backend: Widget-Events als Observation einspeisen | `executor`, `context_manager` | M |
| 7 | Native Tool `render_widget` (optional) | `infrastructure/tools/native/` | S |
| 8 | E2E-Tests (Playwright) für Roundtrip | `ui/e2e/` | M |
| 9 | Dokumentation & ADR | `docs/adr/`, `docs/features/` | S |

---

## 4. Story 1 — A2UI-Schema im Backend

**Datei(en):** neues `src/taskforce/core/domain/widget.py`.
**Inhalt:** Pydantic-Modelle, die 1:1 zu `ui/src/features/chat/widgets/types.ts`
passen (Image, List, Table, Buttons, Card). Union-Diskriminator: `kind`.
**Akzeptanz:** Schema ist via OpenAPI exportiert; `MessagePart` wird auch
backend-seitig als Union aus `text | widget` modelliert.

---

## 5. Story 2 — Stream-Event `widget`

Erweitert `useChatStream.ts` und das SSE-Schema um `event_type: "widget"` mit
`details = { widget_id, widget: WidgetSpec }`. Reihenfolge bleibt erhalten —
Widgets liegen relativ zu den `llm_token`-Events im Stream.

**Akzeptanz:** UI baut `parts: MessagePart[]` aus dem gestreamten Mix von Text
und Widgets korrekt zusammen, ohne den bestehenden Token-Pfad zu brechen.

---

## 6. Story 3 — Widget-Emit-API

Tools und Skills brauchen einen Weg, Widgets zu erzeugen. Optionen:
- Rückgabewert eines Tools darf neben dem üblichen Text auch `widgets: [...]`
  enthalten.
- Neues natives `render_widget` Tool als low-friction Pfad.

**Akzeptanz:** Mindestens ein Beispiel-Skill (z. B. "Termin bestätigen") rendert
einen Buttons-Widget.

---

## 7. Story 4 — Stream-Reader

`useChatStream.ts` sammelt Widgets parallel zu Tokens und reicht sie als `parts`
an die persistierte Nachricht weiter. Pending-Nachricht zeigt Widgets sofort an.

---

## 8. Story 5 — Events zurück an den Agent

Neuer Endpoint:

```
POST /api/v1/conversations/{id}/widget-events
{ "message_id": "...", "widget_id": "...", "kind": "button.pressed", "action_id": "..." }
```

UI ruft `onWidgetEvent` (bereits in `MessageContent`) → POST → Server reicht das
Event als Observation in den Agent-Loop.

**Wichtig:** Events nur einmal feuern (Idempotenz via `(message_id, widget_id, action_id)`).

---

## 9. Story 6 — Observation in den Agent-Loop

Im `executor` wird ein eingehendes Widget-Event in eine Tool-Result-ähnliche
Message gewandelt und über den `ContextManager` an den nächsten LLM-Call
gehängt. Der Agent kann darauf reagieren wie auf ein Tool-Result.

---

## 10. Story 7 — Native Tool `render_widget`

Convenience-Tool, das ein einzelnes `WidgetSpec` validiert und als Stream-Event
ausgibt. Macht es trivial, in einer Skill-Antwort interaktive Elemente zu
platzieren, ohne die Tool-Result-Konvention auszureizen.

---

## 11. Story 8 — E2E-Tests

Playwright-Test in `ui/e2e/`:
1. Mocked SSE-Stream liefert Buttons-Widget.
2. Klick auf Button feuert POST.
3. Assertion: Server hat das Event als Observation gespeichert.

---

## 12. Story 9 — Dokumentation & ADR

Neuer ADR `adr-021-a2ui-widgets.md` (Begründung für A2UI-Anlehnung statt
Custom-Schema), Feature-Doku in `docs/features/widgets.md`, Verweis aus
`README.md` auf die neue Capability.

---

## 13. Out of Scope (für diese Epic)

- Form-Widgets mit komplexer Validierung (eigene Folge-Epic).
- Widget-Streaming mit Partial-Updates (z. B. Live-Tabellen).
- Vollständige A2UI-Protokoll-Konformität — wir spiegeln nur die Kern-Primitiven.
