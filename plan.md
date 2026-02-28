# Plan: Integration von `taskforce_extensions` in `taskforce`

## Ausgangssituation

Aktuell gibt es zwei separate Packages:
- `src/taskforce/` — Hauptpaket (4-Layer Clean Architecture)
- `src/taskforce_extensions/` — Erweiterungspaket mit Infrastructure-Implementierungen, Configs, Plugins und Skills

Die Extensions enthalten ausschließlich **Layer-2-Komponenten** (Infrastructure) sowie Konfigurationsdateien, die bereits über Lazy-Imports in `taskforce` eingebunden werden. Die Integration ist architektonisch sauber möglich, da alle Extensions die richtige Abhängigkeitsrichtung einhalten (Extensions → Core/Interfaces).

---

## Schritt 1: Infrastructure-Code verschieben

Die Python-Module aus `taskforce_extensions/infrastructure/` werden in die bestehende `taskforce/infrastructure/`-Struktur integriert:

| Quelle (extensions) | Ziel (taskforce) | Anmerkung |
|---|---|---|
| `infrastructure/communication/` (6 Dateien) | `taskforce/infrastructure/communication/` | Neues Unterverzeichnis in taskforce/infrastructure |
| `infrastructure/messaging/in_memory_bus.py` | `taskforce/infrastructure/messaging/` | Neues Unterverzeichnis |
| `infrastructure/runtime/` (3 Dateien) | `taskforce/infrastructure/runtime/` | Neues Unterverzeichnis |

**Architektur-Konformität:** Alle diese Module implementieren Protocols aus `core/interfaces/` und importieren nur aus `core/` — das ist Layer-2-konform. Kein Architekturverstoß.

---

## Schritt 2: Configs verschieben

| Quelle | Ziel | Anmerkung |
|---|---|---|
| `taskforce_extensions/configs/*.yaml` | `taskforce/configs/` | Neues Verzeichnis unter `src/taskforce/` |
| `taskforce_extensions/configs/custom/*.yaml` | `taskforce/configs/custom/` | Unterverzeichnis mitverschieben |
| `taskforce_extensions/configs/llm_config.yaml` | `taskforce/configs/llm_config.yaml` | |

**Hinweis:** Configs sind keine Python-Module, sondern YAML-Dateien. Sie gehören nicht direkt zu einer der 4 Schichten, sondern sind Konfigurationsdaten. Innerhalb des `taskforce`-Pakets als `taskforce/configs/` ist ein passender Ort.

---

## Schritt 3: Plugins verschieben

| Quelle | Ziel | Anmerkung |
|---|---|---|
| `taskforce_extensions/plugins/` | `taskforce/plugins/` | Gesamtes Plugin-Verzeichnis |

Plugins sind eigenständige Einheiten mit eigenen Configs, Tools und Skills. Sie werden per Directory-Scanning entdeckt (`plugin_scanner.py`). Der Pfad muss in der Discovery-Logik aktualisiert werden.

---

## Schritt 4: Skills verschieben

| Quelle | Ziel | Anmerkung |
|---|---|---|
| `taskforce_extensions/skills/` | `taskforce/skills/` | Neues Verzeichnis (4 Skill-Verzeichnisse) |

Skills sind Markdown-Dateien mit optionalen Scripts. Kein Python-Package-Aspekt.

---

## Schritt 5: Alle Imports aktualisieren

### 5a. Lazy-Imports in `taskforce` (6 Stellen)

**`src/taskforce/application/infrastructure_builder.py`** (4 Stellen):
```python
# ALT:
from taskforce_extensions.infrastructure.communication.gateway_registry import build_gateway_components
from taskforce_extensions.infrastructure.runtime import ...
from taskforce_extensions.infrastructure.messaging import InMemoryMessageBus

# NEU:
from taskforce.infrastructure.communication.gateway_registry import build_gateway_components
from taskforce.infrastructure.runtime import ...
from taskforce.infrastructure.messaging import InMemoryMessageBus
```

**`src/taskforce/api/cli/simple_chat.py`** (2 Stellen):
```python
# ALT:
from taskforce_extensions.infrastructure.communication.gateway_registry import build_gateway_components
from taskforce_extensions.infrastructure.communication.telegram_poller import TelegramPoller

# NEU:
from taskforce.infrastructure.communication.gateway_registry import build_gateway_components
from taskforce.infrastructure.communication.telegram_poller import TelegramPoller
```

### 5b. Pfad-Referenzen aktualisieren (~15 Stellen)

Alle Dateien, die `src/taskforce_extensions/` als Pfad-String referenzieren, müssen aktualisiert werden:

| Datei | Was ändert sich |
|---|---|
| `application/factory.py` | Config-Verzeichnis: `src/taskforce_extensions/configs/` → `src/taskforce/configs/` |
| `application/profile_loader.py` | Fallback LLM config path |
| `application/infrastructure_builder.py` | Config- und LLM-Config-Pfade |
| `application/agent_registry.py` | Config-Dir und Plugin-Dir |
| `application/plugin_loader.py` | Plugin-Pfad-Migration (Backward-Compat) |
| `infrastructure/persistence/plugin_scanner.py` | Plugin-Scan-Verzeichnis |
| `api/routes/health.py` | Config-Verzeichnis für Health-Checks |
| `api/cli/commands/config.py` | Default Config-Verzeichnis |
| `api/cli/commands/skills.py` | Extension Skills-Verzeichnis |

### 5c. Interne Imports in den verschobenen Dateien

Die Dateien in `taskforce_extensions/infrastructure/` importieren bereits aus `taskforce.core.*` — diese Imports bleiben unverändert. Es gibt **keine internen `taskforce_extensions`-zu-`taskforce_extensions`-Imports**, daher entsteht kein zirkuläres Abhängigkeitsproblem.

---

## Schritt 6: Tests aktualisieren

| Quelle | Ziel |
|---|---|
| `tests/unit/taskforce_extensions/` | `tests/unit/infrastructure/` (in passende Unterverzeichnisse integrieren) |
| `tests/taskforce_extensions/plugins/` | `tests/plugins/` oder `tests/unit/infrastructure/plugins/` |

Alle `from taskforce_extensions.*`-Imports in Tests (~8 Dateien) auf `from taskforce.*` ändern.

---

## Schritt 7: Package-Konfiguration bereinigen

### 7a. `__init__.py`-Dateien

- Neue `__init__.py` für `taskforce/infrastructure/communication/`, `taskforce/infrastructure/messaging/`, `taskforce/infrastructure/runtime/` erstellen (Inhalte aus den Extensions-`__init__.py` übernehmen)
- `src/taskforce_extensions/` komplett entfernen

### 7b. `pyproject.toml`

- `pyproject.toml` prüfen: Hatchling erkennt automatisch alle Packages unter `src/`. Da `taskforce_extensions` als separates Top-Level-Package existiert, muss nach dem Verschieben nichts Spezielles konfiguriert werden — die neuen Unterverzeichnisse werden automatisch Teil von `taskforce`.
- Coverage-Konfiguration prüfen (`--cov=taskforce` erfasst bereits alles)

### 7c. Backward-Compatibility Shim (optional)

Ein temporäres `src/taskforce_extensions/__init__.py` könnte als Deprecation-Shim dienen:

```python
import warnings
warnings.warn(
    "taskforce_extensions is deprecated. Import from taskforce directly.",
    DeprecationWarning,
    stacklevel=2,
)
from taskforce.infrastructure.communication import *  # noqa
```

**Empfehlung:** Nur nötig, wenn externe Nutzer direkt aus `taskforce_extensions` importieren. Wenn es nur intern genutzt wird, kann es sofort entfernt werden.

---

## Schritt 8: Dokumentation aktualisieren

- `CLAUDE.md`: Extensions-Abschnitt entfernen, Struktur-Diagramm aktualisieren
- `README.md`: Referenzen auf `taskforce_extensions` entfernen
- `docs/architecture.md` und relevante Sharded Pages aktualisieren
- `docs/plugins.md`: Plugin-Pfade aktualisieren
- `docs/features/skills.md`: Skill-Pfade aktualisieren
- `docs/profiles.md`: Config-Pfade aktualisieren

---

## Schritt 9: Validierung

1. **Tests ausführen:** `uv run pytest` — alle Tests müssen grün sein
2. **Linting:** `uv run ruff check src/taskforce tests`
3. **Type-Check:** `uv run mypy src/taskforce`
4. **Import-Prüfung:** Sicherstellen, dass kein `taskforce_extensions`-Import mehr existiert (außer optionalem Compat-Shim)
5. **CLI-Test:** `taskforce --help` und `taskforce run mission --profile dev` testen

---

## Zusammenfassung der Änderungen

| Aktion | Anzahl Dateien |
|---|---|
| Python-Dateien verschieben (infrastructure) | ~15 Dateien |
| YAML-Configs verschieben | ~18 Dateien |
| Skills verschieben (Markdown + Scripts) | ~13 Dateien |
| Plugins verschieben | ~30+ Dateien |
| Import-Anpassungen in `taskforce` | ~9 Dateien |
| Import-Anpassungen in Tests | ~8 Dateien |
| Neue `__init__.py` erstellen | 3 Dateien |
| Dokumentation aktualisieren | ~6 Dateien |
| **Gesamt** | **~100 Datei-Operationen** |

## Risiken

- **Kein Architekturverstoß:** Alle verschobenen Infrastructure-Module implementieren nur Core-Protocols → Layer-2-konform
- **Kein zirkulärer Import:** Extensions importieren nie aus Application/API
- **Plugin-Discovery:** Plugin-Scanner-Pfade müssen korrekt aktualisiert werden, sonst finden Plugins ihre Configs nicht
- **Relative Pfade in YAMLs:** Einige YAML-Configs referenzieren Pfade relativ (z.B. `llm_config.yaml`-Pfad in Profilen) — diese müssen geprüft und ggf. angepasst werden
