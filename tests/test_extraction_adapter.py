"""Anthropic adapter unit tests — API-free (D-5): a stub stands in for the
SDK client; live model calls belong only to the milestone-5 eval script."""

import base64
from types import SimpleNamespace

import anthropic
import httpx
import pydantic
import pytest
from helpers import make_application, make_extraction

import ttb_label_reviewer.extraction.anthropic_adapter as adapter
from ttb_label_reviewer.engine import ExtractionResult, review
from ttb_label_reviewer.extraction import (
    DEFAULT_MODEL,
    EXTRACTION_PROMPT,
    AnthropicExtractor,
    ExtractionError,
    LabelImage,
    OfflineExtractor,
    build_client,
    extractor_from_env,
)

PNG = LabelImage(filename="front.png", media_type="image/png", data=b"png-bytes")
JPEG = LabelImage(filename="back.jpg", media_type="image/jpeg", data=b"jpeg-bytes")


class StubClient:
    """Quacks like anthropic.Anthropic for messages.parse only."""

    def __init__(self, response=None, error=None):
        self.parse_kwargs = None

        def parse(**kwargs):
            self.parse_kwargs = kwargs
            if error is not None:
                raise error
            return response

        self.messages = SimpleNamespace(parse=parse)


def ok_response(extraction=None):
    return SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=extraction if extraction is not None else make_extraction(),
    )


def test_returns_parsed_extraction_result():
    client = StubClient(response=ok_response())
    result = AnthropicExtractor(client=client).extract([PNG])
    assert isinstance(result, ExtractionResult)
    assert result.brand_name.raw == "OLD TOM DISTILLERY"


def test_request_carries_all_images_in_order_plus_instruction():
    client = StubClient(response=ok_response())
    AnthropicExtractor(client=client).extract([PNG, JPEG])
    kwargs = client.parse_kwargs
    content = kwargs["messages"][0]["content"]
    image_blocks = [b for b in content if b["type"] == "image"]
    assert [b["source"]["media_type"] for b in image_blocks] == [
        "image/png",
        "image/jpeg",
    ]
    assert image_blocks[0]["source"]["data"] == base64.standard_b64encode(
        b"png-bytes"
    ).decode("ascii")
    assert content[-1]["type"] == "text"
    assert kwargs["system"] == EXTRACTION_PROMPT
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["output_format"] is ExtractionResult


def test_model_is_overridable():
    client = StubClient(response=ok_response())
    AnthropicExtractor(model="claude-haiku-4-5", client=client).extract([PNG])
    assert client.parse_kwargs["model"] == "claude-haiku-4-5"


def test_refusal_stop_reason_raises_extraction_error():
    response = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    with pytest.raises(ExtractionError, match="declined"):
        AnthropicExtractor(client=StubClient(response=response)).extract([PNG])


def test_max_tokens_stop_reason_raises_extraction_error():
    response = SimpleNamespace(stop_reason="max_tokens", parsed_output=None)
    with pytest.raises(ExtractionError, match="cut off"):
        AnthropicExtractor(client=StubClient(response=response)).extract([PNG])


def test_missing_parsed_output_raises_extraction_error():
    response = SimpleNamespace(stop_reason="end_turn", parsed_output=None)
    with pytest.raises(ExtractionError, match="no extraction result"):
        AnthropicExtractor(client=StubClient(response=response)).extract([PNG])


def test_validation_error_surfaces_as_extraction_error():
    # The contract types reject e.g. confidence > 1; the adapter must
    # surface that as a visible error, never a crash.
    try:
        ExtractionResult.model_validate({"brand_name": {"raw": "X", "confidence": 2.0}})
        raise AssertionError("expected contract validation to fail")
    except pydantic.ValidationError as exc:
        validation_error = exc
    client = StubClient(error=validation_error)
    with pytest.raises(ExtractionError, match="malformed"):
        AnthropicExtractor(client=client).extract([PNG])


def test_api_connection_error_surfaces_as_extraction_error():
    error = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    with pytest.raises(ExtractionError, match="request failed"):
        AnthropicExtractor(client=StubClient(error=error)).extract([PNG])


def test_authentication_error_gets_pointed_message():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError(
        "invalid x-api-key",
        response=httpx.Response(401, request=request),
        body=None,
    )
    with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
        AnthropicExtractor(client=StubClient(error=error)).extract([PNG])


# --- backend selection (D-10.1): config picks the Claude endpoint -----------
# These stub the client classes so no credential-requiring SDK client is
# ever constructed; they prove the dispatch, not the SDK.


def test_registry_maps_each_backend_to_its_sdk_client():
    assert adapter._CLIENTS["anthropic"] is anthropic.Anthropic
    assert adapter._CLIENTS["bedrock"] is anthropic.AnthropicBedrock
    assert adapter._CLIENTS["vertex"] is anthropic.AnthropicVertex


def test_build_client_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown EXTRACTOR_BACKEND"):
        build_client("openai")


def test_build_client_dispatches_by_backend(monkeypatch):
    for backend in ("anthropic", "bedrock", "vertex"):
        marker = object()
        monkeypatch.setitem(adapter._CLIENTS, backend, lambda m=marker: m)
        assert build_client(backend) is marker


def test_extractor_from_env_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("EXTRACTOR_BACKEND", raising=False)
    marker = object()
    monkeypatch.setitem(adapter._CLIENTS, "anthropic", lambda: marker)
    extractor = extractor_from_env()
    assert isinstance(extractor, AnthropicExtractor)
    assert extractor._client is marker
    assert extractor.model == DEFAULT_MODEL


def test_extractor_from_env_honors_backend(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_BACKEND", "vertex")
    marker = object()
    monkeypatch.setitem(adapter._CLIENTS, "vertex", lambda: marker)
    assert extractor_from_env()._client is marker


def test_extractor_from_env_offline_backend(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_BACKEND", "offline")
    assert isinstance(extractor_from_env(), OfflineExtractor)


def test_offline_extractor_makes_no_call_and_routes_to_needs_review():
    # No network, no model: every field comes back at zero confidence, so
    # the engine routes the whole review to needs_review — offline mode
    # never fabricates a pass or fail.
    result = OfflineExtractor().extract([PNG])
    assert isinstance(result, ExtractionResult)
    assert result.brand_name.confidence == 0.0
    assert result.government_warning.confidence == 0.0
    review_result = review(make_application(), result)
    assert review_result.verdict.value == "needs_review"
    assert review_result.counts.fail == 0
    assert review_result.counts.pass_ == 0
