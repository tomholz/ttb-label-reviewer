"""Anthropic implementation of the extraction interface.

This is the only module that talks to the vision API (D-10.1): a
production deployment swaps this adapter for a FedRAMP-authorized
endpoint via config, not a rewrite. The model returns the contracts.md
§3 shape as structured output; all parsing and all verdicts stay in the
rule engine (D-1).
"""

import base64
from collections.abc import Sequence

import anthropic
import pydantic

from ..engine import ExtractionResult
from .base import ExtractionError, LabelImage
from .prompt import EXTRACTION_PROMPT

# Overridable per instance; recorded in the eval scoreboard (D-5), so a
# model change is a measured decision, not a silent one.
DEFAULT_MODEL = "claude-opus-4-8"

# The §3 result is a few hundred tokens; headroom for a long warning
# transcription without inviting runaway output.
_MAX_OUTPUT_TOKENS = 2048


class AnthropicExtractor:
    """Vision extraction via the Anthropic API.

    The client resolves ANTHROPIC_API_KEY from the environment; pass
    `client` explicitly only in tests or in tooling that needs its own
    retry policy (the eval runner waits out rate limits; the UI must not).
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self._client = client or anthropic.Anthropic()

    def extract(self, images: Sequence[LabelImage]) -> ExtractionResult:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.standard_b64encode(image.data).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append(
            {
                "type": "text",
                "text": f"Transcribe the fields from this label set "
                f"of {len(images)} image(s).",
            }
        )
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=_MAX_OUTPUT_TOKENS,
                system=EXTRACTION_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=ExtractionResult,
            )
        except pydantic.ValidationError as exc:
            # Engine types enforce the contract at the boundary
            # (confidence 0-1 etc.); malformed model output surfaces as
            # a visible error, never a crash.
            raise ExtractionError(
                "The vision model returned a malformed extraction result; "
                "try again or review this label manually."
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise ExtractionError(
                "Vision API authentication failed — the server's "
                "ANTHROPIC_API_KEY is missing or invalid."
            ) from exc
        except anthropic.APIError as exc:
            raise ExtractionError(f"Vision API request failed: {exc}") from exc

        if response.stop_reason == "refusal":
            raise ExtractionError(
                "The vision model declined to process these images; "
                "review this label manually."
            )
        if response.stop_reason == "max_tokens":
            raise ExtractionError(
                "The vision model's response was cut off before completing "
                "the extraction; try again or review this label manually."
            )
        if response.parsed_output is None:
            raise ExtractionError(
                "The vision model returned no extraction result; "
                "try again or review this label manually."
            )
        return response.parsed_output
