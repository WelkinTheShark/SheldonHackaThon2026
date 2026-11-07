"""U1: the comparison document's worked examples must stay true."""
import pytest

from app import config
from app.costs import call_cost, usage_cost


def test_commit_message_on_opus():
    assert call_cost(config.OPUS, 3_000, 200) == pytest.approx(0.0160, abs=1e-9)


def test_commit_message_on_haiku():
    assert call_cost(config.HAIKU, 3_000, 200) == pytest.approx(0.0004, abs=1e-9)


def test_commit_message_monthly_saving():
    opus = call_cost(config.OPUS, 3_000, 200) * 3_000
    haiku = call_cost(config.HAIKU, 3_000, 200) * 3_000
    assert opus == pytest.approx(48.00)
    assert haiku == pytest.approx(1.20)
    assert opus - haiku == pytest.approx(46.80)


def _retry_loop_cost(calls: int) -> float:
    return sum(call_cost(config.SONNET, 10_000 + 500 * i, 300) for i in range(calls))


def test_retry_loop_of_twenty_calls():
    assert _retry_loop_cost(20) == pytest.approx(0.65)


def test_retry_loop_stopped_after_three():
    assert _retry_loop_cost(3) == pytest.approx(0.072)
    assert _retry_loop_cost(20) - _retry_loop_cost(3) == pytest.approx(0.578)


def test_haiku_long_prompt_rate():
    assert call_cost(config.HAIKU, 100_000, 0) == pytest.approx(0.01)
    assert call_cost(config.HAIKU, 100_001, 0) == pytest.approx(0.0500005)


def test_cached_tokens_use_cache_rates():
    usage = {
        "input_tokens": 1_000,
        "output_tokens": 0,
        "cache_read_input_tokens": 1_000,
        "cache_creation_input_tokens": 1_000,
    }
    assert usage_cost(config.OPUS, usage) == pytest.approx(0.0092)


def test_unknown_model_has_no_price():
    assert call_cost("not-a-model", 1, 1) is None
