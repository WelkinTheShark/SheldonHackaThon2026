"""The use-case table from the plan. Wren runs W1-W6 in a real browser; these guard the API."""
import json

import httpx
import pytest

from app import config, roast

SIMPLE = "Write a commit message for: fix typo in README"
DESIGN = "Design a multi-region failover architecture for a payments ledger."
TOKEN = {"x-api-key": "gateway-secret"}
BODY = {
    "model": config.OPUS,
    "max_tokens": 100,
    "messages": [{"role": "user", "content": SIMPLE}],
}


def send(client, prompt=SIMPLE, model=config.OPUS):
    return client.post("/api/playground", json={"model": model, "prompt": prompt})


def summary(client):
    return client.get("/api/summary").json()


def test_w1_catch_and_fix_overkill(client, anthropic):
    first = send(client).json()
    assert first["status"] == "Overkill"
    assert first["call"]["model"] == config.OPUS
    assert summary(client)["saved"] == 0

    client.put("/api/settings", json={"use_recommended": True})
    second = send(client).json()
    assert second["status"] == "Downshifted"
    assert second["call"]["model"] == config.HAIKU
    assert anthropic.models == [config.OPUS, config.HAIKU]
    # 30 input, 60 output on Opus ($0.00132) minus Haiku ($0.000033).
    assert summary(client)["saved"] == pytest.approx(0.001287)


def test_w2_enforce_a_budget(client, anthropic):
    client.put("/api/settings", json={"budget_usd": 0.0001})
    assert send(client).json()["status"] == "Overkill"
    spent = summary(client)["spent"]

    blocked = send(client).json()
    assert blocked["status"] == "Blocked by budget"
    assert summary(client)["spent"] == spent
    assert len(anthropic.requests) == 1

    client.put("/api/settings", json={"budget_usd": 1.0})
    assert send(client).json()["status"] == "Overkill"
    assert len(anthropic.requests) == 2


def test_w3_stop_a_retry_loop(client, anthropic):
    assert client.post("/api/simulate-loop").json()["statuses"] == [
        "OK", "OK", "OK", "Loop stopped",
    ]
    assert len(anthropic.requests) == 3
    assert anthropic.models == [config.HAIKU] * 3
    assert summary(client)["blocked"] == 1
    assert summary(client)["saved"] > 0


def test_w4_roast_a_prompt(client, anthropic):
    text = "You are an expert. Please summarize this. Please summarize this."
    result = client.post("/api/roast", json={"text": text}).json()
    assert result["score"] < 100
    assert result["issues"]
    assert result["fix"] == "stub reply"
    assert result["receipt"]["model"] == "Haiku 5.5"
    assert result["receipt"]["cost_usd"] > 0
    assert "skipped" in result["receipt"]["note"]


@pytest.mark.parametrize(
    "text, model",
    [
        ("Write a commit message for: fix typo in README", config.HAIKU),
        ("Design a multi-region failover architecture and list the failure modes.", config.OPUS),
        ("Summarize this meeting transcript.", config.SONNET),
        ("Design a commit message format for our team.", config.OPUS),
    ],
)
def test_w4_roast_recommends_a_model(client, anthropic, text, model):
    result = client.post("/api/roast", json={"text": text}).json()
    assert result["recommendation"]["model"] == model
    assert result["recommendation"]["label"] == config.MODEL_LABELS[model]
    assert result["recommendation"]["reason"]
    assert model in config.PLAYGROUND_MODELS


def test_w4_recommended_model_is_never_flagged_overkill(client, anthropic):
    text = "Design a commit message format for our team."
    model = client.post("/api/roast", json={"text": text}).json()["recommendation"]["model"]
    call = client.post("/api/playground", json={"model": model, "prompt": text}).json()
    assert call["status"] == "OK"


def test_w4_tool_definitions_are_not_recommended_haiku(client, anthropic):
    tools = json.dumps([{"name": "format_json", "description": "Format JSON"}])
    result = client.post("/api/roast", json={"text": tools}).json()
    assert result["recommendation"]["model"] == config.SONNET


def test_w4_recommendation_survives_a_claude_failure(client, anthropic):
    anthropic.status = 500
    text = "Write a commit message for: fix typo in README"
    result = client.post("/api/roast", json={"text": text}).json()
    assert result["receipt"]["model"] == "Rules only"
    assert result["recommendation"]["model"] == config.HAIKU


def set_level(client, level):
    return client.put("/api/settings", json={"level": level})


def recommended(client, text):
    return client.post("/api/roast", json={"text": text}).json()["recommendation"]["model"]


def test_w7_level_moves_unclear_work_to_faster_models(client, anthropic):
    text = "Summarize this meeting transcript."
    expected = {1: config.HAIKU, 2: config.SONNET, 3: config.OPUS, 4: config.OPUS}
    for level, model in expected.items():
        set_level(client, level)
        assert recommended(client, text) == model


def test_w7_full_power_keeps_routine_work_on_haiku(client, anthropic):
    set_level(client, 4)
    for text in [SIMPLE, "git push origin main", "What is the default Postgres port?"]:
        assert recommended(client, text) == config.HAIKU
    assert recommended(client, "Format this list as a table") == config.OPUS


def test_w7_investigation_outranks_a_lookup_at_every_level(client, anthropic):
    for level in config.LEVELS:
        set_level(client, level)
        assert recommended(client, "What is causing this? Investigate the logs.") != config.HAIKU
        assert recommended(client, "Where is the bug in the push hook?") != config.HAIKU


def test_w7_level_drives_the_overkill_flag_and_downshift(client, anthropic):
    text = "Summarize this meeting transcript."
    set_level(client, 3)
    assert send(client, text).json()["status"] == "OK"
    set_level(client, 1)
    assert send(client, text).json()["status"] == "Overkill"
    client.put("/api/settings", json={"use_recommended": True})
    assert send(client, text).json()["status"] == "Downshifted"
    set_level(client, 4)
    assert send(client, "Format this list as a table").json()["status"] == "OK"


def test_w7_rejects_an_unknown_level_and_reset_restores_the_default(client, anthropic):
    assert set_level(client, 9).status_code == 400
    set_level(client, 4)
    client.post("/api/reset")
    assert summary(client)["level"] == config.DEFAULT_LEVEL


def test_w4_long_setups_use_sonnet(client, anthropic):
    tools = json.dumps({"tools": [{"name": f"tool_{i}"} for i in range(20)]})
    result = client.post("/api/roast", json={"text": tools}).json()
    assert result["receipt"]["model"] == "Sonnet 5.5"
    assert any("20 tools" in issue for issue in result["issues"])


def test_w4_roast_still_works_when_claude_fails(client, anthropic):
    anthropic.status = 500
    result = client.post("/api/roast", json={"text": "Do the thing."}).json()
    assert result["fix"] == roast.FALLBACK_FIX
    assert result["receipt"]["model"] == "Rules only"
    assert result["issues"]


def test_w5_real_work_is_not_flagged(client, anthropic):
    client.put("/api/settings", json={"use_recommended": True})
    result = send(client, DESIGN).json()
    assert result["status"] == "OK"
    assert anthropic.models == [config.OPUS]


def test_w6_first_visit(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Send call" in page.text
    assert "No calls yet" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/calls").json() == []


def test_e1_empty_prompt(client, anthropic):
    response = send(client, "   ")
    assert response.status_code == 400
    assert response.json()["error"] == "Enter a prompt before sending."
    assert anthropic.requests == []
    assert summary(client)["calls"] == 0


def test_e1_unlisted_model_and_long_prompt(client, anthropic):
    assert send(client, model="claude-fable-5-1").status_code == 400
    assert send(client, "x" * 8_001).status_code == 400
    assert anthropic.requests == []


def test_e2_upstream_error(client, anthropic):
    anthropic.status = 529
    result = send(client).json()
    assert result["status"] == "Error"
    assert "529" in result["message"]
    assert summary(client)["spent"] == 0

    anthropic.status = 200
    assert send(client).json()["status"] == "Overkill"


def test_e2_upstream_unreachable(client, anthropic):
    anthropic.error = httpx.ConnectError("no route")
    result = send(client).json()
    assert result["status"] == "Error"
    assert "Could not reach" in result["message"]


def test_e3_proxy_needs_a_token(client, anthropic):
    assert client.post("/v1/messages", json=BODY).status_code == 401
    wrong = client.post("/v1/messages", json=BODY, headers={"x-api-key": "guess"})
    assert wrong.status_code == 401
    assert anthropic.requests == []


def test_e3_proxy_stays_closed_without_a_configured_token(client, anthropic):
    config.settings.gateway_token = ""
    response = client.post("/v1/messages", json=BODY, headers={"x-api-key": ""})
    assert response.status_code == 401
    assert anthropic.requests == []


def test_e4_reset(client, anthropic):
    client.put("/api/settings", json={"budget_usd": 3, "use_recommended": True})
    send(client)
    client.post("/api/reset")
    state = summary(client)
    assert (state["spent"], state["saved"], state["calls"]) == (0, 0, 0)
    assert state["budget_usd"] == config.DEFAULT_BUDGET_USD
    assert state["use_recommended"] is False
    assert client.get("/api/calls").json() == []


def test_proxy_forwards_body_and_headers_unchanged(client, anthropic):
    raw = json.dumps({**BODY, "future_field": {"a": 1}}, indent=2).encode()
    response = client.post(
        "/v1/messages",
        content=raw,
        headers={**TOKEN, "anthropic-beta": "some-beta", "anthropic-version": "2023-06-01"},
    )
    assert response.status_code == 200
    sent = anthropic.requests[0]
    assert sent.content == raw
    assert sent.headers["anthropic-beta"] == "some-beta"
    assert sent.headers["x-api-key"] == "upstream-secret"


def test_proxy_labels_overkill_but_never_rewrites(client, anthropic):
    client.put("/api/settings", json={"use_recommended": True})
    client.post("/v1/messages", json=BODY, headers=TOKEN)
    assert anthropic.models == [config.OPUS]
    assert client.get("/api/calls").json()[0]["status"] == "Overkill"


def test_proxy_accepts_bearer_token(client):
    headers = {"authorization": "Bearer gateway-secret"}
    assert client.post("/v1/messages", json=BODY, headers=headers).status_code == 200


def test_proxy_block_tells_clients_not_to_retry(client):
    client.put("/api/settings", json={"budget_usd": 0})
    response = client.post("/v1/messages", json=BODY, headers=TOKEN)
    assert response.status_code == 429
    assert response.headers["x-should-retry"] == "false"
    assert response.json()["error"]["type"] == "rate_limit_error"


def test_reset_cannot_bypass_the_hard_cap(client, anthropic):
    config.settings.hard_cap_usd = 0.0001
    send(client)
    client.post("/api/reset")
    result = send(client).json()
    assert result["status"] == "Demo limit reached"
    assert len(anthropic.requests) == 1


def test_refusal_is_labeled(client, anthropic):
    anthropic.stop_reason = "refusal"
    assert send(client).json()["status"] == "Refused"


def test_negative_budget_is_rejected(client):
    assert client.put("/api/settings", json={"budget_usd": -1}).status_code == 400
