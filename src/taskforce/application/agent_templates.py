"""
Agent Templates
===============

Curated starting points for non-technical users creating agents through the
UI wizard. Each template bundles a recommended capability set, a system-prompt
skeleton in plain language, and example test prompts so the user can try the
agent immediately.

Templates are intentionally Python data (not YAML on disk) — they describe how
the wizard should pre-fill the form, not how the agent is persisted. Once the
wizard is finished, the resulting agent is saved as a regular profile/custom
agent through the existing endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass

from taskforce.application.skill_service import get_skill_service
from taskforce.application.tool_registry import get_tool_registry


@dataclass(frozen=True)
class AgentTemplate:
    """A starting point shown as a card in the wizard's step 1."""

    id: str
    name: str
    description: str
    emoji: str
    persona_hint: str
    recommended_tools: tuple[str, ...]
    recommended_skills: tuple[str, ...]
    system_prompt_template: str
    example_prompts: tuple[str, ...]
    tone_default: str = "professionell"
    language_default: str = "Deutsch"


_BUCHHALTER = AgentTemplate(
    id="buchhalter",
    name="Buchhalter-Assistent",
    description=(
        "Hilft beim Erfassen von Belegen, Buchungssätzen und einfachen "
        "Buchhaltungsfragen. Liest PDFs und Excel-Tabellen, schlägt Konten vor."
    ),
    emoji="🧾",
    persona_hint=(
        "z.B. 'Hilf mir beim Erfassen von Bürobedarf-Rechnungen' oder "
        "'Welches Konto nehme ich für eine Hotelübernachtung?'"
    ),
    recommended_tools=(
        "file_read",
        "file_write",
        "excel",
        "docx",
        "wiki",
        "ask_user",
    ),
    recommended_skills=("pdf-processing",),
    system_prompt_template=(
        "Du bist ein präziser Buchhaltungs-Assistent.\n"
        "\n"
        "Deine Aufgaben:\n"
        "- Belege und Rechnungen analysieren\n"
        "- Buchungssätze nach SKR03/SKR04 vorschlagen\n"
        "- Bei Unklarheiten gezielt nachfragen\n"
        "- Beträge immer mit zwei Nachkommastellen angeben\n"
        "- Niemals raten — wenn das Konto unklar ist, frage nach\n"
    ),
    example_prompts=(
        "Ich habe eine Rechnung für Bürobedarf über 47,50 €. Welche Konten?",
        "Erkläre mir den Unterschied zwischen Konto 4980 und 6815.",
        "Wie buche ich eine Bewirtung mit Kunden?",
    ),
)


_HANDWERKER = AgentTemplate(
    id="handwerker",
    name="Angebote & Rechnungen",
    description=(
        "Erstellt Angebote, Aufmaße und Rechnungen für Handwerksbetriebe. "
        "Rechnet mit qm-Preisen, Material und Stunden, exportiert nach Word/Excel."
    ),
    emoji="🛠️",
    persona_hint=(
        "z.B. 'Erstelle ein Angebot für Wohnzimmer 25qm streichen, "
        "Premium-Farbe' oder 'Schreibe eine Rechnung für Auftrag #42'"
    ),
    recommended_tools=(
        "file_read",
        "file_write",
        "edit",
        "docx",
        "excel",
        "wiki",
        "ask_user",
    ),
    recommended_skills=(),
    system_prompt_template=(
        "Du bist ein hilfsbereiter Assistent für einen Handwerksbetrieb.\n"
        "\n"
        "Deine Aufgaben:\n"
        "- Angebote und Rechnungen erstellen\n"
        "- Aufmaße in Quadratmeter, laufende Meter etc. umrechnen\n"
        "- Realistische Stundensätze und Materialpreise verwenden\n"
        "- Die Anrede und Schlussformel höflich, aber direkt halten\n"
        "- Beträge stets mit MwSt. ausweisen\n"
        "- Alle Beträge mit zwei Nachkommastellen\n"
    ),
    example_prompts=(
        "Erstelle ein Angebot für 25qm Wohnzimmer streichen mit Premium-Farbe.",
        "Schreibe eine Rechnung für: Bad fliesen 8qm, 2 Tage Arbeit, 2 Helfer.",
        "Wie viel Farbe brauche ich für 60qm Wand bei 2 Anstrichen?",
    ),
)


_ASSISTENT = AgentTemplate(
    id="assistent",
    name="Persönlicher Assistent",
    description=(
        "Hilft im Alltag — beantwortet Fragen, fasst Texte zusammen, "
        "merkt sich Wichtiges, schreibt E-Mails. Wenn du Butler installiert hast, "
        "kann er auch Termine und Erinnerungen verwalten."
    ),
    emoji="🤝",
    persona_hint=(
        "z.B. 'Fasse mir diese E-Mail zusammen' oder 'Erinnere mich morgen "
        "um 9 Uhr an die Steuerunterlagen'"
    ),
    recommended_tools=(
        "file_read",
        "file_write",
        "edit",
        "web_search",
        "wiki",
        "ask_user",
    ),
    recommended_skills=(),
    system_prompt_template=(
        "Du bist ein freundlicher persönlicher Assistent.\n"
        "\n"
        "Deine Aufgaben:\n"
        "- Fragen klar und kompakt beantworten\n"
        "- Texte und E-Mails zusammenfassen\n"
        "- Auf Wunsch im selben Stil wie der Nutzer schreiben\n"
        "- Wichtige Fakten ins Wiki merken, wenn der Nutzer das sagt\n"
        "- Bei Unklarheiten lieber kurz nachfragen statt raten\n"
    ),
    example_prompts=(
        "Fasse mir diesen Text in drei Bulletpoints zusammen.",
        "Schreibe eine höfliche Absage für eine Einladung am Samstag.",
        "Was sind die Kernaussagen dieser PDF-Datei?",
    ),
)


_RECHERCHE = AgentTemplate(
    id="recherche",
    name="Recherche-Assistent",
    description=(
        "Sucht im Web, fasst Quellen zusammen und erstellt Recherche-Briefings "
        "mit Quellenangaben. Speichert Erkenntnisse im Wiki."
    ),
    emoji="🔎",
    persona_hint=(
        "z.B. 'Recherchiere die aktuellen Trends bei Heizungssanierung' oder "
        "'Vergleiche die Top-3-Anbieter für CRM-Software unter 50 €/Monat'"
    ),
    recommended_tools=(
        "web_search",
        "web_fetch",
        "file_read",
        "file_write",
        "wiki",
        "ask_user",
    ),
    recommended_skills=(),
    system_prompt_template=(
        "Du bist ein gründlicher Recherche-Assistent.\n"
        "\n"
        "Deine Aufgaben:\n"
        "- Im Web nach belastbaren Quellen suchen\n"
        "- Mehrere Quellen gegenchecken, nicht der ersten Treffer trauen\n"
        "- Zusammenfassungen mit Quellenangabe (URL + Veröffentlichungsdatum) erstellen\n"
        "- Bei widersprüchlichen Aussagen die Widersprüche klar benennen\n"
        "- Wichtige Erkenntnisse im Wiki ablegen\n"
    ),
    example_prompts=(
        "Recherchiere die aktuellen Förderungen für Wärmepumpen in Bayern.",
        "Vergleiche die drei meistgenutzten Buchhaltungs-SaaS für Kleinbetriebe.",
        "Was sind die wichtigsten DSGVO-Updates der letzten 12 Monate?",
    ),
)


_BLANK = AgentTemplate(
    id="blank",
    name="Eigener Agent",
    description=(
        "Starte mit einem leeren Agenten und konfiguriere alles selbst. "
        "Empfohlen, wenn du genau weißt, was du brauchst."
    ),
    emoji="✨",
    persona_hint="z.B. 'Ich brauche einen Agenten der …'",
    recommended_tools=("ask_user",),
    recommended_skills=(),
    system_prompt_template="Du bist ein hilfsbereiter Assistent.\n",
    example_prompts=("Hallo, was kannst du?",),
)


_TEMPLATES: tuple[AgentTemplate, ...] = (
    _BUCHHALTER,
    _HANDWERKER,
    _ASSISTENT,
    _RECHERCHE,
    _BLANK,
)


def _available_skill_names() -> set[str]:
    """Return skill names that the local SkillService can resolve.

    Failures here (no skills configured, file IO error) degrade to an empty
    set rather than raising — the wizard works fine without skills.
    """
    try:
        service = get_skill_service()
        return {meta.name for meta in service.get_all_metadata()}
    except Exception:  # noqa: BLE001
        return set()


def list_templates() -> list[AgentTemplate]:
    """Return all available templates, filtering tools and skills the server can't resolve.

    The registry varies by which agent packages are installed (e.g. butler).
    For each template we drop tools and skills that the running server can't
    actually resolve, so the wizard never offers a capability that would fail
    at agent build.
    """
    available_tools = set(get_tool_registry().get_native_tool_names())
    available_skills = _available_skill_names()

    filtered: list[AgentTemplate] = []
    for template in _TEMPLATES:
        kept_tools = tuple(t for t in template.recommended_tools if t in available_tools)
        kept_skills = tuple(
            s for s in template.recommended_skills if s in available_skills
        )
        if kept_tools == template.recommended_tools and kept_skills == template.recommended_skills:
            filtered.append(template)
        else:
            filtered.append(
                AgentTemplate(
                    id=template.id,
                    name=template.name,
                    description=template.description,
                    emoji=template.emoji,
                    persona_hint=template.persona_hint,
                    recommended_tools=kept_tools,
                    recommended_skills=kept_skills,
                    system_prompt_template=template.system_prompt_template,
                    example_prompts=template.example_prompts,
                    tone_default=template.tone_default,
                    language_default=template.language_default,
                )
            )
    return filtered


def get_template(template_id: str) -> AgentTemplate | None:
    """Return a single template by id, or ``None`` if it doesn't exist.

    Iterates ``_TEMPLATES`` directly to skip the per-call registry lookup that
    ``list_templates()`` performs. The capability filtering is reapplied so
    callers still get a server-resolvable result.
    """
    base = next((t for t in _TEMPLATES if t.id == template_id), None)
    if base is None:
        return None
    available_tools = set(get_tool_registry().get_native_tool_names())
    available_skills = _available_skill_names()
    kept_tools = tuple(t for t in base.recommended_tools if t in available_tools)
    kept_skills = tuple(s for s in base.recommended_skills if s in available_skills)
    if kept_tools == base.recommended_tools and kept_skills == base.recommended_skills:
        return base
    return AgentTemplate(
        id=base.id,
        name=base.name,
        description=base.description,
        emoji=base.emoji,
        persona_hint=base.persona_hint,
        recommended_tools=kept_tools,
        recommended_skills=kept_skills,
        system_prompt_template=base.system_prompt_template,
        example_prompts=base.example_prompts,
        tone_default=base.tone_default,
        language_default=base.language_default,
    )
