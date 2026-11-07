"""Every Claude Code prompt gets one rules-only roast, shown live on the page."""
from app import config
from .test_claude_code import call, first_body, hints, tool_round


def live(client):
    return [row for row in client.get("/api/roasts").json() if row["source"] == "live"]


def test_main_prompt_is_roasted_once(client, anthropic, developer):
    auth, _ = developer
    body = first_body("Please write a commit message for: fix typo in README")
    call(client, body, auth, **hints())
    call(client, tool_round(body), auth, **hints())

    rows = live(client)
    assert len(rows) == 1
    row = rows[0]
    assert row["developer"] == "Ada"
    assert row["prompt"] == "Please write a commit message for: fix typo in README"
    assert 0 <= row["score"] < 100
    assert "Politeness or role filler adds tokens without detail." in row["issues"]
    assert row["recommendation"]["label"] == config.MODEL_LABELS[config.HAIKU]
    assert row["recommendation"]["decided_by"] == "Rules"
    assert row["fix"] == "" and row["receipt"] is None
    assert len(anthropic.requests) == 2  # the roast itself made no extra call


def test_live_roast_shows_on_its_history_row(client, developer):
    auth, _ = developer
    call(client, first_body("Commit and push"), auth, **hints())
    row = client.get("/api/history").json()[0]
    assert row["roast"]["id"] == live(client)[0]["id"]


def test_each_new_prompt_gets_its_own_roast(client, developer):
    auth, _ = developer
    call(client, first_body("Commit and push"), auth, **hints("p1"))
    call(client, first_body("Design the cache layer"), auth, **hints("p2"))
    assert [row["prompt"] for row in live(client)] == ["Design the cache layer", "Commit and push"]


def test_background_and_playground_calls_are_not_auto_roasted(client, developer):
    auth, _ = developer
    for request_class in ("subagent", "compaction", "auxiliary"):
        call(client, first_body("Commit and push"), auth, **hints(request_class, request_class))
    client.post("/api/playground", json={"model": config.OPUS, "prompt": "Commit and push"})
    assert live(client) == []


def test_snippet_is_short_and_reset_clears(client, developer):
    auth, _ = developer
    call(client, first_body("x " * 200), auth, **hints())
    assert len(live(client)[0]["prompt"]) <= config.SNIPPET_CHARS
    client.post("/api/reset")
    assert client.get("/api/roasts").json() == []
