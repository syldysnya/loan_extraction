from pathlib import Path

import pytest
from google.genai import types as gemini
from hydra import compose, initialize_config_dir
from hydra.utils import instantiate
from openai.types import CompletionUsage
from openai.types.completion_usage import PromptTokensDetails

from app.extraction.llm import (
    GeminiClient,
    ImagePart,
    OpenAIClient,
    Pricing,
    TextPart,
    Usage,
    _gemini_part,
    _openai_part,
    gemini_usage,
    openai_usage,
)
from app.extraction.tracking import TrackedModel

CONF_DIR = str(Path(__file__).parents[3] / "conf")


def test_cost_prices_cached_input_separately():
    pricing = Pricing(input_per_1m=1.0, cached_input_per_1m=0.1, output_per_1m=10.0)
    usage = Usage(input_tokens=1_000_000, cached_input_tokens=400_000, output_tokens=100_000)

    # 600k uncached × $1 + 400k cached × $0.10 + 100k output × $10, per 1M
    assert pricing.cost(usage) == pytest.approx(0.6 + 0.04 + 1.0)


def test_gemini_usage_counts_thinking_as_output():
    meta = gemini.GenerateContentResponseUsageMetadata(
        prompt_token_count=1000, cached_content_token_count=200, candidates_token_count=50, thoughts_token_count=30
    )

    assert gemini_usage(meta) == Usage(input_tokens=1000, cached_input_tokens=200, output_tokens=80)


def test_openai_usage():
    usage = CompletionUsage(
        prompt_tokens=1000,
        completion_tokens=50,
        total_tokens=1050,
        prompt_tokens_details=PromptTokensDetails(cached_tokens=300),
    )

    assert openai_usage(usage) == Usage(input_tokens=1000, cached_input_tokens=300, output_tokens=50)


def test_missing_usage_is_zero():
    assert gemini_usage(None) == openai_usage(None) == Usage()


def test_parts_map_to_each_sdk():
    assert _gemini_part(TextPart("hello")).text == "hello"
    assert _gemini_part(ImagePart(b"png")).inline_data.data == b"png"
    assert _openai_part(TextPart("hello"))["text"] == "hello"
    assert _openai_part(ImagePart(b"png"))["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    ("model", "client_type", "model_id"),
    [("gemini", GeminiClient, "gemini-3.5-flash-lite"), ("openai", OpenAIClient, "gpt-4o-mini")],
)
def test_model_configs_build_a_tracked_model(model, client_type, model_id, conn, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with initialize_config_dir(config_dir=CONF_DIR, version_base="1.3"):
        cfg = compose(config_name="config", overrides=[f"model={model}"])

    tracked = instantiate(cfg.model, conn=conn)

    assert isinstance(tracked, TrackedModel)
    assert tracked.conn is conn
    client = tracked.client
    assert isinstance(client, client_type)
    assert client.model_id == model_id
    assert isinstance(client.pricing, Pricing)
    assert client.supports_image_input
    assert (client.temperature, client.max_output_tokens) == (0.0, 8192)
