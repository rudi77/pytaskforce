# Plugin System Architecture

Taskforce verwendet ein Entry-Point-basiertes Plugin-System, das externe Pakete (wie `taskforce-enterprise`) ermöglicht, die Framework-Funktionalität zu erweitern, ohne den Kerncode zu modifizieren.

## Überblick

```
┌─────────────────────────────────────────────────────────────────┐
│                    Taskforce Base Package                        │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Plugin Discovery │───>│  Plugin Registry │                   │
│  │  (Entry Points)  │    │   (Middleware,   │                   │
│  └──────────────────┘    │    Routers)      │                   │
│           │              └────────┬─────────┘                   │
│           │                       │                              │
│  ┌────────▼──────────────────────▼─────────┐                   │
│  │              FastAPI App                 │                   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  │                   │
│  │  │ Core    │  │ Plugin  │  │ Plugin  │  │                   │
│  │  │ Routes  │  │ Middle- │  │ Routes  │  │                   │
│  │  │         │  │ ware    │  │         │  │                   │
│  │  └─────────┘  └─────────┘  └─────────┘  │                   │
│  └─────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    Entry Points (pyproject.toml)
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│               taskforce-enterprise (Optional)                    │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ EnterprisePlugin │──> Middleware (Auth)                      │
│  │                  │──> Routers (Admin API)                    │
│  │                  │──> Factory Extensions                     │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Plugin-Typen (Entry Points)

Taskforce definiert vier Entry-Point-Gruppen in `pyproject.toml`:

| Entry Point Gruppe | Zweck |
|-------------------|-------|
| `taskforce.plugins` | Haupt-Plugin-Klassen mit Lifecycle-Management |
| `taskforce.middleware` | Direkte Middleware-Registrierung (z.B. Auth) |
| `taskforce.routers` | FastAPI Router für zusätzliche Endpoints |
| `taskforce.factory_extensions` | Erweiterungen für AgentFactory |

### Beispiel: Entry Points in pyproject.toml

```toml
# taskforce-enterprise/pyproject.toml
[project.entry-points."taskforce.plugins"]
enterprise = "taskforce_enterprise.integration.plugin:EnterprisePlugin"

[project.entry-points."taskforce.middleware"]
auth = "taskforce_enterprise.api.middleware.auth:get_auth_middleware"

[project.entry-points."taskforce.routers"]
admin_users = "taskforce_enterprise.api.routes.admin.users:router"
admin_roles = "taskforce_enterprise.api.routes.admin.roles:router"
```

## Plugin Protocol

Plugins müssen das `PluginProtocol` implementieren:

```python
from typing import Protocol, Any, runtime_checkable

@runtime_checkable
class PluginProtocol(Protocol):
    """Protocol das Plugins implementieren müssen."""

    name: str
    version: str

    def initialize(self, config: dict[str, Any]) -> None:
        """Plugin mit Konfiguration initialisieren."""
        ...

    def get_middleware(self) -> list[Any]:
        """Middleware-Klassen für die Anwendung zurückgeben."""
        ...

    def get_routers(self) -> list[Any]:
        """FastAPI Router zurückgeben."""
        ...

    def extend_factory(self, factory: Any) -> None:
        """AgentFactory mit zusätzlichen Capabilities erweitern."""
        ...

    def shutdown(self) -> None:
        """Ressourcen beim Entladen aufräumen."""
        ...
```

## Plugin Discovery Ablauf

```
1. Server Start (lifespan)
         │
         ▼
2. load_all_plugins()
         │
         ├──> entry_points(group="taskforce.plugins")
         │           │
         │           ▼
         │    Für jeden Entry Point:
         │           │
         │           ├──> Plugin-Klasse laden
         │           ├──> Plugin instanziieren
         │           ├──> plugin.initialize(config)
         │           ├──> plugin.get_middleware() → Registry
         │           └──> plugin.get_routers() → Registry
         │
         ▼
3. _register_plugins(app)
         │
         ├──> Middleware zu FastAPI hinzufügen
         └──> Router zu FastAPI hinzufügen

4. App läuft mit Enterprise-Features (wenn installiert)
         │
         ▼
5. Server Shutdown
         │
         └──> shutdown_plugins()
                    │
                    └──> plugin.shutdown() für jeden
```

## Factory Extensions

Plugins können die AgentFactory erweitern, um Agents bei der Erstellung zu modifizieren:

```python
from taskforce.application.factory import register_factory_extension

def my_extension(factory, config: dict, agent) -> Agent:
    """Agent nach Erstellung modifizieren."""
    if agent is not None:
        # Enterprise-Kontext injizieren
        agent._enterprise_user_id = get_current_user().user_id
    return agent

# Bei Plugin-Initialisierung registrieren
register_factory_extension(my_extension)
```

## Abhängigkeitsrichtung

**Kritisch**: Die Abhängigkeitsrichtung muss strikt eingehalten werden:

```
┌──────────────────────────────────┐
│     taskforce-enterprise         │
│   (Optional, Commercial)         │
│                                  │
│   - imports taskforce.core.*     │
│   - implements protocols         │
│   - extends via entry points     │
└──────────────┬───────────────────┘
               │ depends on
               ▼
┌──────────────────────────────────┐
│         taskforce                │
│   (Base, Open Source)            │
│                                  │
│   - KEINE imports von enterprise │
│   - definiert Protocols          │
│   - Plugin Discovery via EPs     │
└──────────────────────────────────┘
```

## Dateien im Base Package

| Datei | Zweck |
|-------|-------|
| `application/plugin_discovery.py` | Plugin Discovery und Registry |
| `core/interfaces/identity_stubs.py` | Minimale Identity-Protocols für Type-Checking |

## Prüfen ob Enterprise verfügbar

```python
from taskforce.application.plugin_discovery import is_enterprise_available

if is_enterprise_available():
    print("Enterprise-Features aktiv")
else:
    print("Nur Basis-Features")
```

## Installation und Aktivierung

```bash
# Nur Base-Framework
pip install taskforce
# oder
uv pip install taskforce

# Mit Enterprise-Features (Auto-Discovery)
pip install taskforce-enterprise
# Enterprise-Plugin wird automatisch geladen
```

Nach Installation von `taskforce-enterprise` werden die Enterprise-Features automatisch aktiviert - keine Code-Änderungen erforderlich.

## Siehe auch

- [Enterprise Features](../features/enterprise.md) - Enterprise-Funktionalitäten
- [ADR-003: Enterprise Transformation](../adr/adr-003-enterprise-transformation.md) - Architektur-Entscheidungen
