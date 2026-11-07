"""Every Claude Code prompt gets one rules-only roast, shown live on the page."""
from app import config
from .test_claude_code import call, first_body, hints, tool_round


def live(client):
    return client.get("/api/live-roasts").json()


def test_main_prompt_is_roasted_once(client, anthropic, developer):
    auth, _ = developer
    body = first_body("Please write a commit message for: fix typo in README")
    call(client, body, auth, **hints())
    call(client, tool_round(body), auth, **hints())

    rows = live(client)
    assert len(rows) == 1
    row = rows[0]
    assert row["developer"] == "Ada"
    assert row["snippet"] == "Please write a commit message for: fix typo in README"
    assert 0 <= row["score"] < 100
    assert "Politeness or role filler adds tokens without detail." in row["issues"]
    assert row["ideal_label"] == config.MODEL_LABELS[config.HAIKU]
    assert row["decided_by"] == "Rules"
    assert len(anthropic.requests) == 2  # the roast itself made no extra call


def test_each_new_prompt_gets_its_own_roast(client, developer):
    auth, _ = developer
    call(client, first_body("Commit and push"), auth, **hints("p1"))
    call(client, first_body("Design the cache layer"), auth, **hints("p2"))
    assert [row["prompt_id"] for row in live(client)] == ["p2", "p1"]


def test_background_and_playground_calls_are_not_roasted(client, developer):
    auth, _ = developer
    for request_class in ("subagent", "compaction", "auxiliary"):
        call(client, first_body("Commit and push"), auth, **hints(request_class, request_class))
    client.post("/api/playground", json={"model": config.OPUS, "prompt": "Commit and push"})
    client.post("/api/roast", json={"text": "Commit and push"})
    assert live(client) == []


def test_snippet_is_short_and_reset_clears(client, developer):
    auth, _ = developer
    call(client, first_body("x " * 200), auth, **hints())
    assert len(live(client)[0]["snippet"]) <= config.SNIPPET_CHARS + 1
    client.post("/api/reset")
    assert live(client) == []
