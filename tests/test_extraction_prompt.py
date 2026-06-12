"""D-2 enforcement: the canonical warning text never appears in any model
prompt. These tests are the guard rail against a future 'improve the
prompt' pass innocently priming the extractor."""

import re
from pathlib import Path

import ttb_label_reviewer.extraction.prompt as prompt_module
from ttb_label_reviewer.engine.canonical import CANONICAL_LEAD_IN, CANONICAL_WARNING
from ttb_label_reviewer.extraction.prompt import EXTRACTION_PROMPT, prompt_sha256


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_canonical_warning_not_in_prompt():
    canonical = _collapse(CANONICAL_WARNING).lower()
    assert canonical not in _collapse(EXTRACTION_PROMPT).lower()


def test_distinctive_warning_fragments_not_in_prompt():
    # Any one of these in the prompt is partial priming toward the
    # canonical wording — the failure mode DS-5a/5b are most exposed to.
    for fragment in (
        "surgeon general",
        "birth defects",
        "during pregnancy",
        "drive a car",
        "operate machinery",
        "health problems",
    ):
        assert fragment not in EXTRACTION_PROMPT.lower(), fragment


def test_capitalized_lead_in_not_in_prompt():
    # Stricter than D-2's letter: the model's prior on the lead-in is
    # all-caps, so even the two capitalized words would prime extraction
    # to "correct" a title-case label — the exact DS-5b probe case.
    assert CANONICAL_LEAD_IN not in EXTRACTION_PROMPT


def test_prompt_module_does_not_import_canonical():
    # The prompt module must never import the canonical text, even for
    # something innocent-looking like "strip it back out".
    source = Path(prompt_module.__file__).read_text()
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert import_lines == ["import hashlib"], import_lines


def test_prompt_demands_literal_transcription():
    lowered = EXTRACTION_PROMPT.lower()
    assert "exactly as printed" in lowered
    assert "never correct" in lowered


def test_prompt_hash_is_stable_sha256():
    assert prompt_sha256() == prompt_sha256()
    assert re.fullmatch(r"[0-9a-f]{64}", prompt_sha256())
