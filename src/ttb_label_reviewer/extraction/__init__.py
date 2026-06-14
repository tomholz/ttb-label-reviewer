"""Extraction adapter: vision model -> contracts.md §3 extraction result.

The interface lives in base.py; the Anthropic implementation in
anthropic_adapter.py (the only module that talks to the vision API,
D-10.1). Swapping providers means one new adapter, not a rewrite.
"""

from .anthropic_adapter import (
    DEFAULT_MODEL,
    AnthropicExtractor,
    build_client,
    extractor_from_env,
)
from .base import ExtractionError, Extractor, LabelImage
from .offline import OfflineExtractor
from .prompt import EXTRACTION_PROMPT, prompt_sha256

__all__ = [
    "DEFAULT_MODEL",
    "EXTRACTION_PROMPT",
    "AnthropicExtractor",
    "ExtractionError",
    "Extractor",
    "LabelImage",
    "OfflineExtractor",
    "build_client",
    "extractor_from_env",
    "prompt_sha256",
]
