"""Azure OpenAI environment setup for Inspect AI.

Inspect AI uses different env var names than LiteLLM.
This module maps the existing LiteLLM/Taskforce Azure vars
to the Inspect AI convention so both can coexist.

LiteLLM (Taskforce):          Inspect AI:
  AZURE_API_KEY           →     AZUREAI_OPENAI_API_KEY
  AZURE_API_BASE          →     AZUREAI_OPENAI_BASE_URL
  AZURE_API_VERSION       →     AZUREAI_OPENAI_API_VERSION
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def setup_azure_env() -> None:
    """Map Taskforce Azure env vars to Inspect AI convention.

    Loads .env from the project root if not already loaded,
    then copies AZURE_* vars to AZUREAI_OPENAI_* vars
    (without overwriting if already set).
    """
    # Load .env from project root
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    mapping = {
        "AZURE_API_KEY": "AZUREAI_OPENAI_API_KEY",
        "AZURE_API_BASE": "AZUREAI_OPENAI_BASE_URL",
        "AZURE_API_VERSION": "AZUREAI_OPENAI_API_VERSION",
    }

    for src, dst in mapping.items():
        value = os.environ.get(src, "")
        if value and not os.environ.get(dst):
            os.environ[dst] = value


# Model name mapping: Taskforce alias → Inspect AI model string
# Inspect AI format: "openai/azure/<deployment-name>"
AZURE_MODELS = {
    "main": "openai/azure/gpt-5.2",
    "fast": "openai/azure/gpt-5-mini",
    "powerful": "openai/azure/gpt-4.1",
    "powerful-1": "openai/azure/gpt-5-mini",
    "legacy": "openai/azure/gpt-4.1",
}

# Default model for inspect eval --model
DEFAULT_MODEL = AZURE_MODELS["main"]
