import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Final

from google import genai
from google.genai import types as gemini
from openai import OpenAI
from openai.types import CompletionUsage
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from pydantic import BaseModel

TOKENS_PER_PRICE_UNIT = 1_000_000
PNG_MIME = "image/png"
JSON_MIME = "application/json"

# Message field values (OpenAI; USER_ROLE is also Gemini's).
SYSTEM_ROLE: Final = "system"
USER_ROLE: Final = "user"
TEXT_PART: Final = "text"
IMAGE_PART: Final = "image_url"


class Usage(BaseModel):
    input_tokens: int = 0  # includes cached tokens
    cached_input_tokens: int = 0
    output_tokens: int = 0  # includes thinking tokens


class Pricing(BaseModel):
    """USD per 1M tokens."""

    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float

    def cost(self, usage: Usage) -> float:
        uncached = usage.input_tokens - usage.cached_input_tokens
        return (
            uncached * self.input_per_1m
            + usage.cached_input_tokens * self.cached_input_per_1m
            + usage.output_tokens * self.output_per_1m
        ) / TOKENS_PER_PRICE_UNIT


@dataclass
class TextPart:
    text: str


@dataclass
class ImagePart:
    png: bytes


Part = TextPart | ImagePart


@dataclass
class LLMRequest:
    system_prompt: str
    parts: list[Part]


@dataclass
class RawResponse:
    """The model's JSON text, not yet validated, and what the call used."""

    text: str
    usage: Usage


class LLMRefusal(Exception):
    pass


class LLMClient(ABC):
    def __init__(
        self,
        model_id: str,
        pricing: Pricing,
        supports_image_input: bool,
        temperature: float,
        max_output_tokens: int,
    ):
        self.model_id = model_id
        self.pricing = pricing
        self.supports_image_input = supports_image_input
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @abstractmethod
    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse:
        """Ask for JSON matching `schema`. Validation is the caller's job, so usage is kept even if it fails."""


class GeminiClient(LLMClient):
    def __init__(
        self,
        model_id: str,
        api_key: str,
        pricing: Pricing,
        supports_image_input: bool,
        temperature: float,
        max_output_tokens: int,
    ):
        super().__init__(model_id, pricing, supports_image_input, temperature, max_output_tokens)
        self._client = genai.Client(api_key=api_key)

    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse:
        response = self._client.models.generate_content(
            model=self.model_id,
            contents=gemini.Content(role=USER_ROLE, parts=[_gemini_part(p) for p in request.parts]),
            config=gemini.GenerateContentConfig(
                system_instruction=request.system_prompt,
                response_mime_type=JSON_MIME,
                response_schema=schema,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
            ),
        )
        return RawResponse(text=response.text or "", usage=gemini_usage(response.usage_metadata))


class OpenAIClient(LLMClient):
    def __init__(
        self,
        model_id: str,
        api_key: str,
        pricing: Pricing,
        supports_image_input: bool,
        temperature: float,
        max_output_tokens: int,
    ):
        super().__init__(model_id, pricing, supports_image_input, temperature, max_output_tokens)
        self._client = OpenAI(api_key=api_key)

    def complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawResponse:
        completion = self._client.chat.completions.parse(
            model=self.model_id,
            messages=[
                ChatCompletionSystemMessageParam(role=SYSTEM_ROLE, content=request.system_prompt),
                ChatCompletionUserMessageParam(role=USER_ROLE, content=[_openai_part(p) for p in request.parts]),
            ],
            response_format=schema,
            temperature=self.temperature,
            max_completion_tokens=self.max_output_tokens,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise LLMRefusal(message.refusal)
        return RawResponse(text=message.content or "", usage=openai_usage(completion.usage))


def gemini_usage(meta: gemini.GenerateContentResponseUsageMetadata | None) -> Usage:
    if meta is None:
        return Usage()
    return Usage(
        input_tokens=meta.prompt_token_count or 0,
        cached_input_tokens=meta.cached_content_token_count or 0,
        output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
    )


def openai_usage(usage: CompletionUsage | None) -> Usage:
    if usage is None:
        return Usage()
    details = usage.prompt_tokens_details
    return Usage(
        input_tokens=usage.prompt_tokens,
        cached_input_tokens=(details.cached_tokens or 0) if details else 0,
        output_tokens=usage.completion_tokens,
    )


def _gemini_part(part: Part) -> gemini.Part:
    if isinstance(part, TextPart):
        return gemini.Part.from_text(text=part.text)
    return gemini.Part.from_bytes(data=part.png, mime_type=PNG_MIME)


def _openai_part(part: Part) -> ChatCompletionContentPartParam:
    if isinstance(part, TextPart):
        return ChatCompletionContentPartTextParam(type=TEXT_PART, text=part.text)
    data_url = f"data:{PNG_MIME};base64,{base64.b64encode(part.png).decode()}"
    return ChatCompletionContentPartImageParam(type=IMAGE_PART, image_url=ImageURL(url=data_url))
