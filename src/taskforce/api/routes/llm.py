"""
LLM API Routes
==============

Surfaces the configured model aliases from ``llm_config.yaml`` for use
in the agent editor's "default model" dropdown.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


def _resolve_llm_config_path() -> Path:
    """Locate ``llm_config.yaml`` regardless of how the API was started."""
    here = Path(__file__).resolve()
    project_root = here.parent.parent.parent.parent.parent
    candidate = project_root / "src" / "taskforce" / "configs" / "llm_config.yaml"
    if candidate.is_file():
        return candidate
    fallback = Path.cwd() / "src" / "taskforce" / "configs" / "llm_config.yaml"
    return fallback


class LLMModelEntry(BaseModel):
    alias: str = Field(..., description="Short alias used in profile YAMLs")
    model_id: str = Field(..., description="LiteLLM model string (provider/model)")
    provider: str = Field(..., description="Inferred provider prefix")


class LLMModelsResponse(BaseModel):
    default_model: str
    models: list[LLMModelEntry]


def _infer_provider(model_id: str) -> str:
    if "/" not in model_id:
        return "openai"
    return model_id.split("/", 1)[0]


@router.get(
    "/llm/models",
    response_model=LLMModelsResponse,
    summary="List configured LLM model aliases",
)
def list_llm_models() -> LLMModelsResponse:
    """Return every alias from the active ``llm_config.yaml``."""
    path = _resolve_llm_config_path()
    if not path.is_file():
        return LLMModelsResponse(default_model="main", models=[])

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    default_model = str(data.get("default_model") or "main")
    aliases = data.get("models") or {}
    entries = [
        LLMModelEntry(alias=alias, model_id=str(model_id), provider=_infer_provider(str(model_id)))
        for alias, model_id in aliases.items()
        if isinstance(alias, str)
    ]
    entries.sort(key=lambda e: e.alias)
    return LLMModelsResponse(default_model=default_model, models=entries)
