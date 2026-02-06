"""
Deprecated: Parameter mapping is no longer needed.

LiteLLM's drop_params=True handles unsupported parameters automatically
for all providers. This module is kept for backward compatibility only.
"""


class ParameterMapper:
    """Deprecated: Use LiteLLMService with drop_params=True instead."""

    def __init__(self, **kwargs):
        pass

    def get_model_parameters(self, model: str) -> dict:
        return {}

    def map_for_model(self, model: str, params: dict) -> dict:
        return params

    def validate_params(self, model: str, params: dict) -> tuple:
        return True, []
