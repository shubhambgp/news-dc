"""Provider-neutral LLM interface (PLAN §11.5) and its Anthropic implementation.

Pipeline code depends on `LLMClient` and `LLMError` only, never on a vendor's response shape.
Retries for transient failures (429, 5xx, 529 overloaded, connection errors and timeouts) are done
by the Anthropic SDK itself: bounded by `max_retries`, exponential backoff, and it honours
Retry-After. Whatever still fails is mapped to an `LLMError` that says whether to try again later.
"""

import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
from anthropic.types import MessageParam, OutputConfigParam, TextBlockParam


@dataclass
class LLMResponse:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int  # uncached input
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int


class LLMError(Exception):
    """`retryable`: the item can be tried again in a later run (provider down, rate limited).
    `fatal`: no item can succeed until a human fixes something (bad key, unknown model)."""

    def __init__(self, message: str, *, retryable: bool, fatal: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.fatal = fatal


class LLMClient(Protocol):
    model: str

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResponse: ...


class AnthropicLLM:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: str = "",
        timeout_s: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key or not model:
            raise LLMError(
                "ANTHROPIC_API_KEY and CLASSIFIER_MODEL must be set", retryable=False, fatal=True
            )
        self.model = model
        self.effort = effort
        self.client = anthropic.Anthropic(
            api_key=api_key,
            timeout=anthropic.Timeout(timeout_s, connect=5.0),
            max_retries=max_retries,
        )

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResponse:
        output_config: OutputConfigParam = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort:
            output_config["effort"] = self.effort  # type: ignore[typeddict-item]
        # The long, static system prompt is the cached prefix (identical for every item).
        blocks: list[TextBlockParam] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        started = time.monotonic()
        try:
            r = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=blocks,
                messages=messages,
                output_config=output_config,
            )
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
        ) as exc:
            raise LLMError(_describe(exc), retryable=False, fatal=True) from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(_describe(exc), retryable=False) from exc
        except anthropic.APIStatusError as exc:  # 429/5xx left over after the SDK's retries
            raise LLMError(
                _describe(exc),
                retryable=exc.status_code in (408, 409, 429) or exc.status_code >= 500,
            ) from exc
        except anthropic.APIConnectionError as exc:  # includes APITimeoutError
            raise LLMError(_describe(exc), retryable=True) from exc
        u = r.usage
        return LLMResponse(
            text="".join(b.text for b in r.content if b.type == "text"),
            model=r.model,
            stop_reason=r.stop_reason,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


def _describe(exc: Exception) -> str:
    """Type and status only: never the request, which would contain the prompt (§11.5)."""
    status = getattr(exc, "status_code", None)
    message = getattr(exc, "message", "") or ""
    return f"{type(exc).__name__}{f' {status}' if status else ''}: {message[:300]}"
