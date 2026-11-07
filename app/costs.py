"""Turns token counts into dollars."""
from decimal import Decimal

from . import config


def _rates(model: str, prompt_tokens: int) -> dict | None:
    if model == config.HAIKU and prompt_tokens > config.HAIKU_LONG_PROMPT_TOKENS:
        return config.HAIKU_LONG_PRICES
    return config.PRICES.get(model)


def call_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Return the USD cost of a call, or None when the model has no known price."""
    prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens
    rates = _rates(model, prompt_tokens)
    if rates is None:
        return None
    # Decimal keeps the worked examples exact; float sums drift at the sixth place.
    total = (
        Decimal(input_tokens) * Decimal(str(rates["input"]))
        + Decimal(output_tokens) * Decimal(str(rates["output"]))
        + Decimal(cache_read_tokens) * Decimal(str(rates["cache_read"]))
        + Decimal(cache_write_tokens) * Decimal(str(rates["cache_write"]))
    )
    return float(total / Decimal(1_000_000))


def usage_cost(model: str, usage: dict) -> float | None:
    return call_cost(
        model,
        usage.get("input_tokens", 0) or 0,
        usage.get("output_tokens", 0) or 0,
        usage.get("cache_read_input_tokens", 0) or 0,
        usage.get("cache_creation_input_tokens", 0) or 0,
    )
