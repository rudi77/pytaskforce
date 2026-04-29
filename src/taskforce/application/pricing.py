"""
Pricing
=======

Loads ``configs/pricing.yaml`` and turns prompt/completion token counts
into a USD cost estimate. The table is intentionally separate from
``llm_config.yaml`` so it can drift independently when providers change
prices.

Lookup order for a given model id:

1. Exact match (``"azure/gpt-5.4-mini"``).
2. Provider wildcard (``"ollama/*"``).
3. ``default`` entry — surfaced to the UI as "approximate" pricing.

If even ``default`` is missing the cost is reported as ``0.0`` rather
than raising, so analytics endpoints stay non-blocking when the file is
malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import structlog
import yaml

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m_usd: float
    output_per_1m_usd: float

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ModelPrice":
        return cls(
            input_per_1m_usd=float(raw.get("input_per_1m_usd", 0) or 0),
            output_per_1m_usd=float(raw.get("output_per_1m_usd", 0) or 0),
        )


@dataclass(frozen=True)
class PricingResult:
    cost_usd: float
    matched_model: str
    is_default: bool


class PricingTable:
    """Cost calculator backed by ``pricing.yaml``."""

    def __init__(
        self,
        models: dict[str, ModelPrice],
        default: ModelPrice | None,
        as_of: str | None,
    ) -> None:
        self._models = models
        self._default = default
        self._as_of = as_of

    @property
    def as_of(self) -> str | None:
        return self._as_of

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> PricingResult:
        if not model:
            model = "unknown"
        price = self._lookup(model)
        if price is None:
            return PricingResult(cost_usd=0.0, matched_model=model, is_default=True)
        cost = (
            (prompt_tokens or 0) / 1_000_000 * price.input_per_1m_usd
            + (completion_tokens or 0) / 1_000_000 * price.output_per_1m_usd
        )
        is_default = price is self._default
        return PricingResult(
            cost_usd=cost,
            matched_model=model if not is_default else "default",
            is_default=is_default,
        )

    def _lookup(self, model: str) -> ModelPrice | None:
        if model in self._models:
            return self._models[model]
        if "/" in model:
            provider = model.split("/", 1)[0]
            wildcard = f"{provider}/*"
            if wildcard in self._models:
                return self._models[wildcard]
        return self._default


def load_pricing_table(path: Path | None = None) -> PricingTable:
    """Load the pricing table from disk; fall back to a built-in default."""
    target = path or _default_pricing_path()
    if target.is_file():
        try:
            with target.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            logger.warning("pricing_yaml_invalid", path=str(target), error=str(exc))
            data = {}
    else:
        logger.debug("pricing_yaml_missing", path=str(target))
        data = {}

    models_raw = data.get("models") or {}
    models: dict[str, ModelPrice] = {}
    default: ModelPrice | None = None
    for key, value in models_raw.items():
        if not isinstance(value, dict):
            continue
        price = ModelPrice.from_dict(value)
        if key == "default":
            default = price
        else:
            models[key] = price
    if default is None:
        default = ModelPrice(input_per_1m_usd=1.0, output_per_1m_usd=3.0)
    as_of = data.get("as_of")
    return PricingTable(models=models, default=default, as_of=str(as_of) if as_of else None)


def _default_pricing_path() -> Path:
    here = Path(__file__).resolve()
    project_root = here.parent.parent.parent.parent
    return project_root / "src" / "taskforce" / "configs" / "pricing.yaml"


_table: PricingTable | None = None


def get_pricing_table() -> PricingTable:
    global _table
    if _table is None:
        _table = load_pricing_table()
    return _table


def reset_pricing_table() -> None:
    global _table
    _table = None
