"""The Simulated responses switch: no call leaves the app, and every row says so."""
import pytest

from app import config, jev, simulated, sse, store
from .test_claude_code import call, calls, first_body, hints

SIMPLE = {"model": config.OPUS, "prompt": "Write a commit message for: fix typo in README"}


def simulate(client, on=True):
    assert client.put("/api/settings", json={"simulated": on}).json()["simulated"] is on


def test_off_by_default_and_real_calls_are_not_marked(client):
    assert client.get("/api/summary").json()["simulated"] is False
    client.post("/api/playground", json=SIMPLE)
    assert client.get("/api/history").json()[0]["simulated"] is False


def test_simulated_call_returns_the_canned_reply_and_is_marked(client):
    simulate(client)
    body = client.post("/api/playground", json=SIMPLE).json()

    assert body["status"] == "Overkill"
    assert body["reply"] == simulated.REPLY
    assert body["call"]["simulated"] == 1
    assert client.get("/api/history").json()[0]["simulated"] is True


def test_real_upstream_is_never_used(client, monkeypatch):
    monkeypatch.setattr(config.settings, "upstream", "http://127.0.0.1:1")
    simulate(client)
    assert client.post("/api/playground", json=SIMPLE).json()["reply"] == simulated.REPLY


def test_simulated_cost_counts_toward_budget_but_not_the_hard_cap(client):
    simulate(client)
    client.put("/api/settings", json={"budget_usd": 0.0001})
    assert client.post("/api/playground", json=SIMPLE).json()["status"] == "Overkill"
    assert client.post("/api/playground", json=SIMPLE).json()["status"] == "Blocked by budget"
    assert store.totals()["spent"] > 0
    assert store.lifetime_spend() == 0


def test_hard_cap_does_not_stop_simulated_calls(client, monkeypatch):
    monkeypatch.setattr(config.settings, "hard_cap_usd", 0.0)
    assert client.post("/api/playground", json=SIMPLE).json()["status"] == "Demo limit reached"
    simulate(client)
    assert client.post("/api/playground", json=SIMPLE).json()["status"] == "Overkill"


def test_swap_still_happens(client):
    simulate(client)
    client.put("/api/settings", json={"use_recommended": True})
    row = client.post("/api/playground", json=SIMPLE).json()["call"]
    assert (row["status"], row["model"]) == ("Downshifted", config.HAIKU)
    assert row["saved_usd"] > 0


def test_loop_is_still_stopped(client):
    simulate(client)
    assert client.post("/api/simulate-loop").json()["statuses"][-1] == "Loop stopped"


def test_setting_survives_reset(client):
    simulate(client)
    client.post("/api/reset")
    assert client.get("/api/summary").json()["simulated"] is True


def test_streamed_reply_is_complete_and_recorded(client, developer):
    auth, record = developer
    simulate(client)
    response = call(client, first_body("Commit and push"), auth, **hints())

    reader = sse.StreamReader()
    reader.feed(response.content)
    assert reader.complete and reader.stop_reason == "end_turn"
    row = calls(client)[0]
    assert (row["developer_id"], row["simulated"]) == (record["id"], 1)
    assert row["output_tokens"] == simulated.OUTPUT_TOKENS


def test_count_tokens_stays_local(client, developer, monkeypatch):
    auth, _ = developer
    monkeypatch.setattr(config.settings, "upstream", "http://127.0.0.1:1")
    simulate(client)
    response = client.post("/v1/messages/count_tokens", json=first_body("Hello"), headers=auth)
    assert response.status_code == 200 and response.json()["input_tokens"] > 0


def test_jev_is_skipped(client, fake_jev, monkeypatch):
    async def never(_):
        pytest.fail("Jev was called in simulated mode")

    monkeypatch.setattr(jev, "classify", never)
    simulate(client)
    row = client.post("/api/playground", json=SIMPLE).json()["call"]
    assert row["decided_by"] == "Rules"
