"""Jev judging prompts, and the keyword rules taking over whenever it can't."""
import asyncio

import httpx
import pytest

from app import config, jev
from .conftest import jev_answers

SUMMARY = "Summarize this meeting transcript."


def recommend(client, text=SUMMARY):
    return client.post("/api/roast", json={"text": text}).json()["recommendation"]


@pytest.mark.parametrize(
    "answers, kind",
    [
        (jev_answers("routine"), "routine"),
        (jev_answers("mechanical"), "simple"),
        (jev_answers("unclear"), "grey"),
        (jev_answers("agent_setup"), "heavy"),
        (jev_answers("investigation"), "deep"),
        (jev_answers("design"), "deep"),
        # A likely investigation wins over any other answer.
        (jev_answers("routine", investigate=0.71), "deep"),
        # The middle band rules out the cheap kinds, but not the others.
        (jev_answers("routine", investigate=0.3), "grey"),
        (jev_answers("routine", investigate=0.7), "grey"),
        (jev_answers("mechanical", investigate=0.5), "grey"),
        (jev_answers("agent_setup", investigate=0.5), "heavy"),
        (jev_answers("routine", investigate=0.29), "routine"),
        # Unsure answers fall to the unclear kind.
        (jev_answers("routine", probability=0.69), "grey"),
        (jev_answers("routine", probability=0.7), "routine"),
        (jev_answers("routine", score_confidence=0.49), "grey"),
    ],
)
def test_thresholds(answers, kind):
    assert jev.kind_from(answers) == kind


def test_jev_decides_when_configured(client, fake_jev):
    fake_jev.answers = jev_answers("routine")
    result = recommend(client)
    assert result["model"] == config.HAIKU
    assert result["decided_by"] == "Jev"


def test_jev_verdict_follows_the_routing_bar(client, fake_jev):
    fake_jev.answers = jev_answers("mechanical")
    client.put("/api/settings", json={"level": 4})
    assert recommend(client)["model"] == config.OPUS


def test_call_records_who_judged_it(client, fake_jev):
    fake_jev.answers = jev_answers("design")
    body = {"model": config.OPUS, "prompt": SUMMARY}
    assert client.post("/api/playground", json=body).json()["status"] == "OK"
    call = client.get("/api/calls").json()[0]
    assert (call["ideal_model"], call["decided_by"]) == (config.OPUS, "Jev")


def test_jev_sees_the_human_prompt_and_nothing_else(client, fake_jev):
    recommend(client, "Rename this variable")
    sent = fake_jev.requests[0]
    assert sent["state"] == "Rename this variable"
    assert sent["model"] == config.JEV_MODEL
    assert set(sent["questions"]) == {"task_kind", "complexity", "needs_investigation"}
    assert "unclear" in sent["questions"]["task_kind"]["criteria"]


def test_long_prompts_are_trimmed_before_jev(client, fake_jev):
    recommend(client, "word " * 3_000)
    assert len(fake_jev.requests[0]["state"]) == config.JEV_MAX_STATE_CHARS


def test_tool_definitions_skip_jev(client, fake_jev):
    recommend(client, '[{"name": "format_json"}]')
    assert fake_jev.requests == []


def test_no_key_means_rules_and_no_request(client):
    result = recommend(client)
    assert result["decided_by"] == "Rules"
    assert result["model"] == config.SONNET


@pytest.mark.parametrize("status", [401, 422, 429, 500, 529])
def test_error_statuses_fall_back_to_rules(client, fake_jev, status):
    fake_jev.status = status
    assert recommend(client)["decided_by"] == "Rules"


def test_connection_failure_falls_back_to_rules(client, fake_jev):
    fake_jev.error = httpx.ConnectError("no route")
    assert recommend(client)["decided_by"] == "Rules"


@pytest.mark.parametrize(
    "answers",
    [{}, {"task_kind": {}}, jev_answers("a_kind_we_never_asked_about"), {"task_kind": None}],
)
def test_unexpected_answers_fall_back_to_rules(client, fake_jev, answers):
    fake_jev.answers = answers
    assert recommend(client)["decided_by"] == "Rules"


def test_slow_jev_times_out_and_falls_back(client, fake_jev, monkeypatch):
    async def stall(_):
        await asyncio.sleep(5)

    monkeypatch.setattr(jev, "_ask", stall)
    monkeypatch.setattr(config, "JEV_TIMEOUT_SECONDS", 0.01)
    assert recommend(client)["decided_by"] == "Rules"
