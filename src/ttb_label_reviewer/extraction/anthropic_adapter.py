"""Anthropic implementation of the extraction interface.

This is the only module that talks to the vision API (D-10.1): a
production deployment swaps this adapter for a FedRAMP-authorized
endpoint via config, not a rewrite. The model returns the contracts.md
§3 shape as structured output; all parsing and all verdicts stay in the
rule engine (D-1).
"""

import base64
import os
from collections.abc import Sequence

import anthropic
import pydantic

from ..engine import ExtractionResult
from .base import ExtractionError, Extractor, LabelImage
from .offline import OfflineExtractor
from .prompt import EXTRACTION_PROMPT

# Overridable per instance; recorded in the eval scoreboard (D-5), so a
# model change is a measured decision, not a silent one.
DEFAULT_MODEL = "claude-opus-4-8"

# The §3 result is a few hundred tokens; headroom for a long warning
# transcription without inviting runaway output.
_MAX_OUTPUT_TOKENS = 2048

# All three backends are Claude through the Anthropic SDK (D-10.1): the
# same messages.parse call and the same structured-output contract,
# differing only in how the client authenticates and which endpoint it
# reaches. `anthropic` is the prototype's public API; `bedrock` is Claude
# on AWS Bedrock (GovCloud / FedRAMP High); `vertex` is Claude on GCP.
# Each client reads its own credentials, region, base_url, and proxy
# settings from the environment, so production selects a backend by
# config alone — the seam the federal transition story turns on.
VisionClient = (
    anthropic.Anthropic | anthropic.AnthropicBedrock | anthropic.AnthropicVertex
)

_CLIENTS: dict[str, type] = {
    "anthropic": anthropic.Anthropic,
    "bedrock": anthropic.AnthropicBedrock,
    "vertex": anthropic.AnthropicVertex,
}


class AnthropicExtractor:
    """Vision extraction via the Anthropic API.

    The client resolves ANTHROPIC_API_KEY from the environment; pass
    `client` explicitly only in tests or in tooling that needs its own
    retry policy (the eval runner waits out rate limits; the UI must not).
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: VisionClient | None = None,
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


def build_client(backend: str) -> VisionClient:
    """Construct the SDK client for the chosen backend (D-10.1).

    Raises ValueError on an unknown backend name — an operator
    misconfiguration, surfaced clearly rather than as an opaque failure.
    """
    try:
        client_cls = _CLIENTS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown EXTRACTOR_BACKEND {backend!r}; expected one of "
            f"{', '.join(sorted(_CLIENTS))}."
        ) from None
    return client_cls()


def extractor_from_env() -> Extractor:
    """Build the default extractor from environment config (D-10.1).

    EXTRACTOR_BACKEND selects the Claude endpoint (default `anthropic`);
    `anthropic`/`bedrock`/`vertex` share the same adapter, prompt, and
    contract. `offline` is the no-network backend (no model call), for
    proving zero-outbound boot. This is the seam the federal transition
    story turns on: a production deployment changes one environment
    variable, not the code.
    """
    backend = os.environ.get("EXTRACTOR_BACKEND", "anthropic")
    if backend == "offline":
        return OfflineExtractor()
    return AnthropicExtractor(client=build_client(backend))
