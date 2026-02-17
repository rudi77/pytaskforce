# Auto-Epic Orchestration - Implementierungsplan

**Ziel:** Der Agent erkennt automatisch, ob eine Mission komplex genug ist, um Epic Orchestration (Planner/Worker/Judge) zu benötigen, und wechselt bei Bedarf selbstständig in diesen Modus.

---

## Architektur-Übersicht

```
Mission-Eingabe (CLI / API / Chat)
        │
        ▼
┌───────────────────────────────┐
│  AgentExecutor                │
│  execute_mission_streaming()  │
│        │                      │
│        ▼                      │
│  ┌─────────────────────┐      │
│  │ TaskComplexity-      │      │
│  │ Classifier           │      │
│  │ (LLM-basiert)        │      │
│  └─────┬───────────────┘      │
│        │                      │
│   ┌────┴────┐                 │
│   │         │                 │
│   ▼         ▼                 │
│ SIMPLE    EPIC                │
│   │         │                 │
│   ▼         ▼                 │
│ Standard  EpicOrchestrator    │
│ Agent     .run_epic()         │
│ .execute()                    │
└───────────────────────────────┘
```

**Kern-Idee:** Eine neue Komponente `TaskComplexityClassifier` im Application Layer führt einen schnellen LLM-Call durch, der die Mission-Beschreibung analysiert und entscheidet, ob Epic Orchestration sinnvoll ist. Diese Klassifikation geschieht **vor** der Agent-Erstellung und ist damit für CLI, API und Chat transparent.

---

## Schritt 1: Domain-Modelle erweitern

**Datei:** `src/taskforce/core/domain/epic.py`

### 1.1 Neues Enum `TaskComplexity`

```python
class TaskComplexity(str, Enum):
    """Klassifikation der Aufgaben-Komplexität."""
    SIMPLE = "simple"       # Einzelner Agent reicht aus
    EPIC = "epic"           # Multi-Agent Epic Orchestration nötig
```

### 1.2 Neues Dataclass `TaskComplexityResult`

```python
@dataclass(frozen=True)
class TaskComplexityResult:
    """Ergebnis der Aufgaben-Komplexitäts-Analyse."""
    complexity: TaskComplexity
    reasoning: str                    # LLM-Begründung für die Entscheidung
    confidence: float                 # 0.0 - 1.0
    suggested_worker_count: int       # Vorgeschlagene Anzahl Workers (nur bei EPIC)
    suggested_scopes: list[str]       # Vorgeschlagene Sub-Planner-Scopes (optional)
    estimated_task_count: int         # Geschätzte Anzahl Tasks
```

### 1.3 Neues EventType

**Datei:** `src/taskforce/core/domain/enums.py`

```python
class EventType(str, Enum):
    # ... bestehende Events ...
    EPIC_ESCALATION = "epic_escalation"   # Mission wurde als epic klassifiziert
```

**Begründung:** Das Event informiert CLI/API-Konsumenten, dass die Ausführung zu Epic Orchestration eskaliert wurde, damit die UI passend reagieren kann (z.B. andere Darstellung).

---

## Schritt 2: TaskComplexityClassifier implementieren

**Neue Datei:** `src/taskforce/application/task_complexity_classifier.py`

### 2.1 Classifier-Klasse

```python
class TaskComplexityClassifier:
    """Klassifiziert Missions-Komplexität via LLM-Analyse.

    Entscheidet ob eine Mission als einzelne Agent-Aufgabe (SIMPLE) oder
    als Multi-Agent Epic (EPIC) ausgeführt werden soll.
    """

    CLASSIFICATION_PROMPT = '''...'''  # Siehe 2.2

    def __init__(self, llm_provider: LLMProviderProtocol):
        self._llm = llm_provider

    async def classify(
        self,
        mission: str,
        context: dict[str, Any] | None = None,
    ) -> TaskComplexityResult:
        """Klassifiziert die Komplexität einer Mission.

        Args:
            mission: Mission-Beschreibung
            context: Optionaler Kontext (z.B. verfügbare Tools, Projektstruktur)

        Returns:
            TaskComplexityResult mit Klassifikation und Begründung
        """
```

### 2.2 Classification-Prompt

Der Prompt ist das Herzstück. Er muss dem LLM klare Kriterien geben:

```
Du bist ein Task-Komplexitäts-Analyzer. Analysiere die folgende Aufgabe und
entscheide, ob sie von einem einzelnen Agenten (SIMPLE) oder von einem
Multi-Agent-Team mit Planner/Worker/Judge-Rollen (EPIC) ausgeführt werden soll.

Kriterien für EPIC (Multi-Agent):
- Die Aufgabe besteht aus mehreren unabhängigen Teilaufgaben
- Verschiedene Dateien/Module müssen parallel bearbeitet werden
- Die Aufgabe erfordert unterschiedliche Fähigkeiten (z.B. Recherche + Implementierung + Test)
- Die Aufgabe beschreibt ein Projekt/Feature mit mehreren Komponenten
- Die Aufgabe enthält Begriffe wie "System", "Architektur", "mehrere", "komplett"
- Die geschätzte Anzahl der Teilaufgaben ist > 3

Kriterien für SIMPLE (Einzel-Agent):
- Die Aufgabe ist klar definiert und fokussiert
- Es geht um eine einzelne Datei oder Funktion
- Einfache Recherche, Erklärung oder kleine Änderung
- Die Aufgabe kann in wenigen Schritten erledigt werden
- Fragen beantworten, Code erklären, einzelnen Bug fixen

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt:
{
    "complexity": "simple" oder "epic",
    "reasoning": "Kurze Begründung",
    "confidence": 0.0-1.0,
    "suggested_worker_count": 1-5,
    "suggested_scopes": ["scope1", "scope2"],
    "estimated_task_count": N
}

Aufgabe: {mission}
```

### 2.3 Antwort-Parsing und Fallback

- JSON-Parsing der LLM-Antwort mit Fallback auf SIMPLE bei Parse-Fehlern
- Confidence-Threshold: Nur EPIC wenn `confidence >= 0.7` (konfigurierbar)
- Timeout: Max 10 Sekunden für den Klassifikations-Call
- Fehlerfall: Bei LLM-Fehler → Standard-Modus (SIMPLE) als Fallback

### 2.4 Modell-Wahl

Der Classifier verwendet das `"fast"` Modell-Alias (oder konfigurierbar via `orchestration.classifier_model`), da:
- Die Klassifikation möglichst schnell und günstig sein soll
- Kein Tool-Calling nötig ist (nur strukturierte JSON-Ausgabe)
- Ein kleineres Modell für diese Entscheidung ausreicht

---

## Schritt 3: Konfiguration erweitern

### 3.1 Profile YAML-Schema

**Datei:** `src/taskforce/core/domain/config_schema.py`

Erweiterung des `ProfileConfigSchema`:

```python
class AutoEpicConfig(BaseModel):
    """Konfiguration für automatische Epic-Erkennung."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Aktiviert automatische Epic-Erkennung"
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Mindest-Confidence für Epic-Eskalation"
    )
    classifier_model: str | None = Field(
        default=None,
        description="LLM-Modell-Alias für Classifier (None = default)"
    )
    default_worker_count: int = Field(
        default=3,
        ge=1, le=10,
        description="Standard-Anzahl Workers bei Epic"
    )
    default_max_rounds: int = Field(
        default=3,
        ge=1, le=10,
        description="Standard Max-Rounds bei Epic"
    )
    planner_profile: str = Field(
        default="planner",
        description="Profil für den Planner-Agent"
    )
    worker_profile: str = Field(
        default="worker",
        description="Profil für Worker-Agents"
    )
    judge_profile: str = Field(
        default="judge",
        description="Profil für den Judge-Agent"
    )
```

### 3.2 Beispiel-Profil

```yaml
# dev.yaml - mit Auto-Epic
profile: dev

orchestration:
  auto_epic:
    enabled: true
    confidence_threshold: 0.7
    classifier_model: fast    # Schnelles Modell für Klassifikation
    default_worker_count: 3
    default_max_rounds: 3
    planner_profile: planner
    worker_profile: worker
    judge_profile: judge

agent:
  planning_strategy: native_react
  max_steps: 30
# ...
```

---

## Schritt 4: AgentExecutor integrieren

**Datei:** `src/taskforce/application/executor.py`

### 4.1 Neuer Parameter `auto_epic`

Erweiterung der Signaturen von `execute_mission()` und `execute_mission_streaming()`:

```python
async def execute_mission_streaming(
    self,
    mission: str,
    profile: str = "dev",
    # ... bestehende Parameter ...
    auto_epic: bool | None = None,      # NEU: None = aus Profil lesen
    epic_config: dict[str, Any] | None = None,  # NEU: Override der Epic-Config
) -> AsyncIterator[ProgressUpdate]:
```

### 4.2 Klassifikations-Logik

Einfügung in `execute_mission_streaming()` **nach** dem STARTED-Event aber **vor** der Agent-Erstellung:

```python
async def execute_mission_streaming(self, mission, profile, ...):
    # ... STARTED event ...

    # === NEU: Auto-Epic Klassifikation ===
    should_use_epic = False
    epic_params = None

    if auto_epic is not False:  # None (aus config) oder True (explizit)
        profile_config = self._load_profile_config(profile)
        auto_epic_config = self._get_auto_epic_config(profile_config, epic_config)

        if auto_epic_config and auto_epic_config.enabled:
            classifier = TaskComplexityClassifier(
                llm_provider=self._create_llm_provider(profile_config)
            )
            classification = await classifier.classify(mission)

            if (classification.complexity == TaskComplexity.EPIC
                and classification.confidence >= auto_epic_config.confidence_threshold):

                should_use_epic = True
                epic_params = {
                    "worker_count": classification.suggested_worker_count
                        or auto_epic_config.default_worker_count,
                    "max_rounds": auto_epic_config.default_max_rounds,
                    "planner_profile": auto_epic_config.planner_profile,
                    "worker_profile": auto_epic_config.worker_profile,
                    "judge_profile": auto_epic_config.judge_profile,
                    "sub_planner_scopes": classification.suggested_scopes or None,
                }

                # Event: Eskalation zu Epic
                yield ProgressUpdate(
                    timestamp=datetime.now(),
                    event_type=EventType.EPIC_ESCALATION,
                    message=f"Mission als komplex erkannt → Epic Orchestration "
                            f"({classification.reasoning})",
                    details={
                        "complexity": classification.complexity.value,
                        "confidence": classification.confidence,
                        "reasoning": classification.reasoning,
                        "worker_count": epic_params["worker_count"],
                        "estimated_tasks": classification.estimated_task_count,
                    },
                )

    # === Routing-Entscheidung ===
    if should_use_epic:
        async for update in self._execute_epic_streaming(mission, epic_params):
            yield update
    else:
        # Bestehender Standard-Pfad
        agent = await self._create_agent(profile, ...)
        async for update in self._execute_streaming(agent, mission, session_id):
            yield update
```

### 4.3 Neue Methode `_execute_epic_streaming()`

```python
async def _execute_epic_streaming(
    self,
    mission: str,
    epic_params: dict[str, Any],
) -> AsyncIterator[ProgressUpdate]:
    """Führt Mission als Epic Orchestration aus und yielded Progress-Updates."""
    orchestrator = EpicOrchestrator(factory=self.factory)

    result = await orchestrator.run_epic(
        mission=mission,
        planner_profile=epic_params["planner_profile"],
        worker_profile=epic_params["worker_profile"],
        judge_profile=epic_params["judge_profile"],
        worker_count=epic_params["worker_count"],
        max_rounds=epic_params["max_rounds"],
        sub_planner_scopes=epic_params.get("sub_planner_scopes"),
    )

    # Konvertiere EpicRunResult → ProgressUpdate-Events
    yield ProgressUpdate(
        timestamp=datetime.now(),
        event_type=EventType.COMPLETE,
        message=result.judge_summary or "Epic completed",
        details={
            "status": result.status,
            "session_id": result.run_id,
            "run_id": result.run_id,
            "tasks_completed": len([r for r in result.worker_results if r.status == "completed"]),
            "tasks_total": len(result.tasks),
            "rounds": len(result.round_summaries),
            "epic_mode": True,
        },
    )
```

**Hinweis:** Die `_execute_epic_streaming()`-Methode könnte in einer späteren Iteration echtes Streaming liefern (z.B. Progress pro Worker-Task). Für die erste Version reicht ein abschließendes COMPLETE-Event.

---

## Schritt 5: CLI-Integration

**Datei:** `src/taskforce/api/cli/commands/run.py`

### 5.1 Neuer CLI-Parameter

```python
@app.command()
def run_mission(
    mission: str,
    profile: str = "dev",
    # ... bestehende Parameter ...
    auto_epic: Optional[bool] = typer.Option(
        None,
        "--auto-epic/--no-auto-epic",
        help="Automatisch in Epic-Modus wechseln bei komplexen Aufgaben. "
             "Standard: aus Profil-Konfiguration.",
    ),
):
```

### 5.2 Weitergabe an Executor

```python
result = await executor.execute_mission(
    mission=mission,
    profile=profile,
    auto_epic=auto_epic,
    # ...
)
```

### 5.3 UI-Feedback bei Eskalation

Im Streaming-Modus: Spezielle Darstellung des `EPIC_ESCALATION`-Events:

```python
elif event_type == EventType.EPIC_ESCALATION:
    console.print(
        Panel(
            f"[bold yellow]Mission als komplex erkannt[/]\n"
            f"Wechsle zu Epic Orchestration (Planner/Worker/Judge)\n\n"
            f"Begründung: {update.details.get('reasoning', '')}\n"
            f"Workers: {update.details.get('worker_count', 3)}\n"
            f"Geschätzte Tasks: {update.details.get('estimated_tasks', '?')}",
            title="Epic Orchestration",
            border_style="yellow",
        )
    )
```

---

## Schritt 6: API-Integration

**Datei:** `src/taskforce/api/routes/execution.py`

### 6.1 Request-Schema erweitern

```python
class ExecuteMissionRequest(BaseModel):
    # ... bestehende Felder ...
    auto_epic: Optional[bool] = Field(
        default=None,
        description=(
            "Automatische Epic-Erkennung. None=aus Profil, "
            "True=erzwingen, False=deaktivieren."
        ),
    )
```

### 6.2 Weitergabe an Executor

```python
result = await executor.execute_mission(
    mission=request.mission,
    auto_epic=request.auto_epic,
    # ...
)
```

---

## Schritt 7: Tests

### 7.1 Unit Tests für TaskComplexityClassifier

**Neue Datei:** `tests/unit/application/test_task_complexity_classifier.py`

```python
class TestTaskComplexityClassifier:
    """Tests für den Komplexitäts-Classifier."""

    async def test_simple_task_classified_correctly(self, mock_llm):
        """Einfache Aufgabe → SIMPLE."""
        mock_llm.complete.return_value = {
            "success": True,
            "content": json.dumps({
                "complexity": "simple",
                "reasoning": "Single file bug fix",
                "confidence": 0.9,
                "suggested_worker_count": 1,
                "suggested_scopes": [],
                "estimated_task_count": 1,
            }),
        }
        classifier = TaskComplexityClassifier(mock_llm)
        result = await classifier.classify("Fix the typo in README.md")
        assert result.complexity == TaskComplexity.SIMPLE

    async def test_complex_task_classified_as_epic(self, mock_llm):
        """Komplexe Aufgabe → EPIC."""
        mock_llm.complete.return_value = {
            "success": True,
            "content": json.dumps({
                "complexity": "epic",
                "reasoning": "Multi-component system with API, DB, and frontend",
                "confidence": 0.95,
                "suggested_worker_count": 4,
                "suggested_scopes": ["api", "database", "frontend", "tests"],
                "estimated_task_count": 8,
            }),
        }
        classifier = TaskComplexityClassifier(mock_llm)
        result = await classifier.classify(
            "Build a complete user management system with REST API, "
            "database migrations, frontend forms, and integration tests"
        )
        assert result.complexity == TaskComplexity.EPIC
        assert result.confidence >= 0.7

    async def test_low_confidence_falls_back_to_simple(self, mock_llm):
        """Niedrige Confidence → SIMPLE (Fallback)."""

    async def test_llm_error_falls_back_to_simple(self, mock_llm):
        """LLM-Fehler → SIMPLE (sicherer Fallback)."""

    async def test_invalid_json_falls_back_to_simple(self, mock_llm):
        """Ungültige JSON-Antwort → SIMPLE."""

    async def test_classifier_uses_fast_model(self, mock_llm):
        """Classifier nutzt das konfigurierte Modell."""
```

### 7.2 Unit Tests für Executor-Integration

**Neue Datei:** `tests/unit/application/test_auto_epic_integration.py`

```python
class TestAutoEpicIntegration:
    """Tests für die Auto-Epic-Integration im Executor."""

    async def test_auto_epic_disabled_by_default(self):
        """Ohne Konfiguration: kein Auto-Epic."""

    async def test_auto_epic_triggers_for_complex_mission(self):
        """Komplexe Mission mit auto_epic=True → EpicOrchestrator."""

    async def test_auto_epic_false_skips_classification(self):
        """auto_epic=False → keine Klassifikation, Standard-Pfad."""

    async def test_epic_escalation_event_emitted(self):
        """EPIC_ESCALATION Event wird bei Eskalation gesendet."""

    async def test_epic_result_converted_to_progress_updates(self):
        """EpicRunResult wird korrekt zu ProgressUpdates konvertiert."""
```

### 7.3 Unit Tests für Konfiguration

**Erweitere:** `tests/unit/core/test_config_schema.py`

```python
class TestAutoEpicConfig:
    def test_auto_epic_config_defaults(self):
        """Standard-Werte sind korrekt."""

    def test_auto_epic_config_validation(self):
        """Validierung der Konfiguration (Thresholds, etc.)."""

    def test_profile_with_auto_epic(self):
        """Profil mit auto_epic-Konfiguration wird korrekt geladen."""
```

---

## Schritt 8: Dokumentation aktualisieren

### 8.1 Bestehende Docs

| Datei | Änderung |
|-------|----------|
| `README.md` | Neuen CLI-Parameter `--auto-epic` dokumentieren |
| `docs/architecture/epic-orchestration.md` | Auto-Epic-Erkennung als neue Capability dokumentieren |
| `docs/cli.md` | `--auto-epic/--no-auto-epic` Flag dokumentieren |
| `docs/api.md` | `auto_epic` Request-Parameter dokumentieren |
| `docs/profiles.md` | `orchestration.auto_epic` Config-Sektion dokumentieren |

### 8.2 Neues ADR

**Datei:** `docs/adr/adr-008-auto-epic-orchestration.md`

Entscheidung: LLM-basierte Klassifikation statt regelbasiert, weil:
- Flexibler bei neuen Aufgabentypen
- Besser bei natürlichsprachlichen Nuancen
- Fallback auf SIMPLE ist sicher und deterministisch

---

## Implementierungs-Reihenfolge

| Phase | Beschreibung | Dateien |
|-------|-------------|---------|
| **Phase 1** | Domain-Modelle | `core/domain/epic.py`, `core/domain/enums.py` |
| **Phase 2** | Config-Schema | `core/domain/config_schema.py` |
| **Phase 3** | Classifier | `application/task_complexity_classifier.py` (neu) |
| **Phase 4** | Executor-Integration | `application/executor.py` |
| **Phase 5** | CLI-Integration | `api/cli/commands/run.py` |
| **Phase 6** | API-Integration | `api/routes/execution.py` |
| **Phase 7** | Tests | `tests/unit/application/` |
| **Phase 8** | Dokumentation | `docs/`, `README.md` |

---

## Architektur-Compliance

| Regel | Status |
|-------|--------|
| Layer-Grenzen eingehalten | `TaskComplexityClassifier` im Application Layer, Models im Core |
| Protocols statt ABC | Nutzt `LLMProviderProtocol` für LLM-Zugriff |
| Keine Infrastructure-Imports in Core | `TaskComplexity` und `TaskComplexityResult` sind reine Domain-Modelle |
| Async für I/O | `classify()` ist async |
| Typ-Annotationen | Überall vorhanden |
| Keine Magic Strings | `TaskComplexity` Enum, `EventType.EPIC_ESCALATION` |
| Fehler-Handling | Graceful Fallback auf SIMPLE bei jeglichen Fehlern |

---

## Offene Design-Entscheidungen

### 1. Streaming bei Epic-Ausführung

**Aktuell:** `_execute_epic_streaming()` liefert nur ein COMPLETE-Event am Ende.

**Zukünftig (Phase 2):** Echtes Streaming könnte implementiert werden, indem der `EpicOrchestrator` selbst `StreamEvent`s yielded (z.B. pro Worker-Fortschritt). Das erfordert eine Refaktorierung des Orchestrators zu einem AsyncIterator-Pattern.

### 2. User-Bestätigung vor Eskalation

**Optional:** Statt automatisch zu eskalieren, könnte der Agent den Benutzer erst fragen ("Diese Aufgabe scheint komplex. Soll ich Epic Orchestration verwenden?"). Dies könnte über den `ask_user`-Mechanismus implementiert werden und wäre als Option `confirm_escalation: true` konfigurierbar.

### 3. Kostenabschätzung

Der zusätzliche LLM-Call für die Klassifikation verursacht geringe Kosten (~100-200 Tokens). Bei dem `fast`-Modell ist das vernachlässigbar. Der Nutzen (Vermeidung ineffizienter Einzelagent-Ausführung bei komplexen Tasks oder unnötiger Multi-Agent-Ausführung bei einfachen Tasks) überwiegt die Kosten deutlich.
