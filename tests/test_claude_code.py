"""Claude Code through the proxy: streaming, attribution, and model swaps with their safeguards."""
import json

import httpx
import pytest

from app import config, sse, store
from .conftest import sse as event, stream_events

SYSTEM = [{"type": "text", "text": "You are Claude Code.", "cache_control": {"type": "ephemeral"}}]
TOOLS = [{"name": "Bash", "description": "Run a command", "input_schema": {"type": "object"}}]
REMINDER = "<system-reminder>Design the architecture and debug why it failed.</system-reminder>"


def first_body(prompt, model=config.OPUS):
    return {
        "model": model,
        "max_tokens": 1024,
        "stream": True,
        "system": SYSTEM,
        "tools": TOOLS,
        "thinking": {"type": "adaptive"},
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": REMINDER}, {"type": "text", "text": prompt}],
        }],
    }


def tool_round(body):
    """The next request of the same prompt: history plus a tool result, no human words."""
    return {
        **body,
        "messages": body["messages"] + [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "done"}],
            },
        ],
    }


def hints(prompt_id="prompt-1", request_class="main"):
    return {"x-claude-code-prompt-id": prompt_id, "x-claude-code-request-class": request_class}


def call(client, body, auth, **headers):
    return client.post("/v1/messages?beta=true", json=body, headers={**auth, **headers})


def turn_on_swaps(client):
    client.put("/api/settings", json={"use_recommended": True})


def calls(client):
    return client.get("/api/calls").json()


def test_stream_bytes_arrive_unchanged_and_usage_is_recorded(client, anthropic, developer):
    auth, record = developer
    anthropic.chunk_size = 7
    response = call(client, first_body("Commit and push"), auth, **hints())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["request-id"] == "req_1"
    assert response.content == b"".join(stream_events(config.OPUS))

    row = calls(client)[0]
    assert row["developer_id"] == record["id"]
    assert (row["input_tokens"], row["output_tokens"]) == (30, 60)
    assert (row["cache_read_tokens"], row["cache_write_tokens"]) == (1000, 200)
    # Opus: 30 x $4 + 60 x $20 + 1000 x $0.20 + 200 x $5, per million.
    assert row["cost_usd"] == pytest.approx(0.00252)


@pytest.mark.parametrize("split", range(1, 200, 13))
def test_reader_handles_chunks_split_anywhere(split):
    raw = b"".join(stream_events(config.OPUS, "refusal"))
    reader = sse.StreamReader()
    reader.feed(raw[:split])
    reader.feed(raw[split:])
    assert reader.complete
    assert reader.stop_reason == "refusal"
    assert reader.usage["output_tokens"] == 60
    assert reader.usage["cache_read_input_tokens"] == 1000


def test_cut_off_stream_stays_cut_off_and_is_recorded_as_dropped(client, anthropic, developer):
    auth, _ = developer
    anthropic.events = stream_events(config.OPUS)[:4]
    response = call(client, first_body("Commit and push"), auth, **hints())
    assert b"message_stop" not in response.content
    row = calls(client)[0]
    assert row["status"] == "Dropped"
    assert row["input_tokens"] == 30


def test_stream_error_event_is_recorded(client, anthropic, developer):
    auth, _ = developer
    anthropic.events = stream_events(config.OPUS)[:2] + [
        event("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Busy"}})
    ]
    response = call(client, first_body("Commit and push"), auth, **hints())
    assert b"overloaded_error" in response.content
    row = calls(client)[0]
    assert (row["status"], row["reason"]) == ("Error", "Busy")


def test_lost_upstream_connection_breaks_the_client_stream(client, anthropic, developer):
    auth, _ = developer
    anthropic.chunk_size, anthropic.fail_after = 50, 100
    with pytest.raises(httpx.ReadError):
        call(client, first_body("Commit and push"), auth, **hints())
    assert calls(client)[0]["status"] == "Error"


def test_limits_apply_before_a_stream_opens(client, anthropic, developer):
    auth, _ = developer
    client.put("/api/settings", json={"budget_usd": 0})
    response = call(client, first_body("Commit and push"), auth, **hints())
    assert response.status_code == 429
    assert response.headers["x-should-retry"] == "false"
    assert anthropic.requests == []


def test_upstream_error_before_streaming_is_passed_on(client, anthropic, developer):
    auth, _ = developer
    anthropic.status = 529
    response = call(client, first_body("Commit and push"), auth, **hints())
    assert response.status_code == 529
    assert calls(client)[0]["status"] == "Error"


def test_headers_query_and_body_are_forwarded(client, anthropic, developer):
    auth, _ = developer
    body = first_body("Commit and push")
    call(client, body, auth, **{"anthropic-beta": "some-beta", "anthropic-version": "2023-06-01"})
    sent = anthropic.requests[0]
    assert sent.url.query == b"beta=true"
    assert sent.headers["anthropic-beta"] == "some-beta"
    assert sent.headers["x-api-key"] == "upstream-secret"
    assert "authorization" not in sent.headers
    assert json.loads(sent.content) == body


def test_count_tokens_and_startup_probe(client, anthropic, developer):
    auth, _ = developer
    assert client.head("/api/hello").status_code == 200
    assert client.post("/v1/messages/count_tokens", json={}).status_code == 401
    response = client.post("/v1/messages/count_tokens?beta=true", json={}, headers=auth)
    assert response.json() == {"input_tokens": 12}
    assert calls(client) == []


def test_injected_reminders_do_not_affect_the_judgement(client, anthropic, developer):
    auth, _ = developer
    call(client, first_body("Commit and push"), auth, **hints())
    row = calls(client)[0]
    assert row["task_kind"] == "routine"
    assert row["ideal_model"] == config.HAIKU
    assert row["prompt_snippet"] == "Commit and push"


def test_claude_code_tools_do_not_make_every_prompt_heavy(client, anthropic, developer):
    auth, _ = developer
    call(client, first_body("Summarize this file"), auth, **hints())
    assert calls(client)[0]["task_kind"] == "grey"


def test_setting_off_labels_but_leaves_the_request_alone(client, anthropic, developer):
    auth, _ = developer
    body = first_body("Commit and push")
    call(client, body, auth, **hints())
    assert anthropic.models == [config.OPUS]
    assert calls(client)[0]["status"] == "Overkill"


def test_swap_changes_only_the_model_and_lasts_the_whole_prompt(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    body = first_body("Commit and push")
    call(client, body, auth, **hints())
    call(client, tool_round(body), auth, **hints())

    assert anthropic.models == [config.HAIKU, config.HAIKU]
    assert json.loads(anthropic.requests[0].content) == {**body, "model": config.HAIKU}
    newest, oldest = calls(client)
    assert oldest["status"] == newest["status"] == "Downshifted"
    assert oldest["saved_usd"] > 0

    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["calls"] == 2
    assert history[0]["used_label"] == "Haiku 5.5"
    assert history[0]["ideal_label"] == "Haiku 5.5"
    assert history[0]["prompt"] == "Commit and push"


def test_each_new_prompt_gets_its_own_decision(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    call(client, first_body("Commit and push"), auth, **hints("one"))
    call(client, first_body("Debug why login fails"), auth, **hints("two"))
    assert anthropic.models == [config.HAIKU, config.OPUS]


@pytest.mark.parametrize("request_class", ["compaction", "auxiliary", "subagent", "workflow"])
def test_background_calls_are_never_swapped_or_rated(client, anthropic, developer, request_class):
    auth, _ = developer
    turn_on_swaps(client)
    call(client, first_body("Commit and push"), auth, **hints(request_class=request_class))
    assert anthropic.models == [config.OPUS]
    row = calls(client)[0]
    assert (row["status"], row["ideal_model"]) == ("OK", "")


def test_keep_tag_overrides_the_swap(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    body = first_body("Commit and push #keep")
    call(client, body, auth, **hints())
    call(client, tool_round(body), auth, **hints())
    assert anthropic.models == [config.OPUS, config.OPUS]
    assert calls(client)[0]["status"] == "Overkill"


def test_developer_can_be_opted_out_of_swaps(client, anthropic, developer):
    auth, record = developer
    turn_on_swaps(client)
    store.set_swaps_allowed(record["name"], False)
    call(client, first_body("Commit and push"), auth, **hints())
    assert anthropic.models == [config.OPUS]


def test_no_prompt_id_means_no_swap(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    call(client, first_body("Commit and push"), auth, **{"x-claude-code-request-class": "main"})
    assert anthropic.models == [config.OPUS]
    assert calls(client)[0]["status"] == "Overkill"


def test_rejected_swap_resends_the_original_bytes_once(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    anthropic.rejected_models = {config.HAIKU}
    body = first_body("Commit and push")
    response = call(client, body, auth, **hints())

    assert response.status_code == 200
    assert anthropic.models == [config.HAIKU, config.OPUS]
    assert json.loads(anthropic.requests[1].content) == body
    assert calls(client)[0]["status"] == "Swap failed"
    assert calls(client)[0]["model"] == config.OPUS

    call(client, tool_round(body), auth, **hints())
    assert anthropic.models == [config.HAIKU, config.OPUS, config.OPUS]


def test_rejection_of_the_requested_model_is_not_retried(client, anthropic, developer):
    auth, _ = developer
    anthropic.rejected_models = {config.OPUS}
    response = call(client, first_body("Commit and push"), auth, **hints())
    assert response.status_code == 400
    assert len(anthropic.requests) == 1


def test_full_power_moves_up_and_costs_more_with_no_saving_shown(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    client.put("/api/settings", json={"level": 4})
    call(client, first_body("Summarize this file", config.HAIKU), auth, **hints())
    assert anthropic.models == [config.OPUS]
    row = calls(client)[0]
    assert row["status"] == "Upshifted"
    assert row["saved_usd"] == 0


def test_non_streaming_swap_works_too(client, anthropic, developer):
    auth, _ = developer
    turn_on_swaps(client)
    body = {**first_body("Commit and push"), "stream": False}
    assert call(client, body, auth, **hints()).status_code == 200
    assert anthropic.models == [config.HAIKU]
