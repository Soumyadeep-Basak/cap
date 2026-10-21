"""Shared prompt loading for the RAG agents.

Prompt personas and instructions live in config/rag_prompts.yaml so
they can be reviewed and tuned without touching agent code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[5]
RAG_PROMPTS_PATH = PROJECT_ROOT / "config" / "rag_prompts.yaml"


@lru_cache(maxsize=1)
def load_rag_prompts() -> dict[str, Any]:
    """Load and cache the RAG prompt templates."""
    with RAG_PROMPTS_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def build_system_prompt(prompt_key: str) -> str:
    """Combine a prompt's persona and instructions into one system prompt."""
    prompts = load_rag_prompts()
    entry = prompts.get(prompt_key, {})

    persona = (entry.get("persona") or "").strip()
    instructions = (entry.get("instructions") or "").strip()

    return f"{persona}\n\n{instructions}".strip()
