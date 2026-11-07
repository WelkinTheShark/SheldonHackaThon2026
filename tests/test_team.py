"""Developers, delivery history, the leaderboard, dev time and storage upgrades."""
import gzip
import json
import sqlite3

import pytest

from app import config, devs, store, team

ROUTINE = "Write a commit message for: fix typo in README"
UNCLEAR = "Summarize this meeting transcript."
ACTIVE = config.ACTIVE_TIME_METRIC


def send(client, developer_id, prompt=ROUTINE, model=config.OPUS, **extra):
    body = {"model": model, "prompt": prompt, "developer_id": developer_id, **extra}
    return client.post("/api/playground", json=body)


def board(client):
    return client.get("/api/leaderboard").json()["rows"]


def row_for(client, name):
    return next(r for r in board(client) if r["developer"] == name)


def metrics(value=120.0, name=ACTIVE, temporality=1):
    return {
        "resourceMetrics": [{
            "scopeMetrics": [{
                "metrics": [{
                    "name": name,
                    "sum": {
                        "aggregationTemporality": temporality,
                        "dataPoints": [{"asDouble": value}],
                    },
                }],
            }],
        }],
    }


def test_tokens_are_stored_hashed(client):
    _, token = store.add_developer("Grace")
    raw = store._db.execute("SELECT token_hash FROM developers").fetchone()["token_hash"]
    assert token not in raw
    assert store.developer_by_token(token)["name"] == "Grace"
    assert store.developer_by_token("guess") is None


def test_developer_token_opens_the_proxy(client, developer):
    auth, _ = developer
    body = {"model": config.HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/v1/messages", json=body, headers=auth).status_code == 200


def test_shared_token_is_recorded_as_unattributed(client):
    body = {"model": config.HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    client.post("/v1/messages", json=body, headers={"x-api-key": "gateway-secret"})
    assert client.get("/api/history").json()[0]["developer"] == team.UNATTRIBUTED
    assert row_for(client, team.UNATTRIBUTED)["rank"] is None


def test_playground_attributes_calls_and_rejects_unknown_developers(client, developer):
    _, record = developer
    assert send(client, record["id"]).status_code == 200
    assert client.get("/api/history").json()[0]["developer"] == "Ada"
    assert send(client, 999).status_code == 400


def test_history_row_lists_ideal_and_used(client, developer):
    _, record = developer
    send(client, record["id"])
    row = client.get("/api/history").json()[0]
    assert (row["ideal_label"], row["used_label"]) == ("Haiku 5.5", "Opus 5.5")
    assert row["prompt"] == ROUTINE
    assert row["decided_by"] == "Rules"


def test_only_a_snippet_of_the_prompt_is_stored(client, developer):
    _, record = developer
    send(client, record["id"], "word " * 100)
    row = client.get("/api/calls").json()[0]
    assert len(row["prompt_snippet"]) == config.SNIPPET_CHARS


def test_anyway_override_keeps_the_chosen_model(client, anthropic, developer):
    _, record = developer
    client.put("/api/settings", json={"use_recommended": True})
    send(client, record["id"], keep_model=True)
    send(client, record["id"])
    assert anthropic.models == [config.OPUS, config.HAIKU]


def test_any_model_above_ideal_is_overkill_and_can_move_up_or_down(client, anthropic, developer):
    _, record = developer
    assert send(client, record["id"], UNCLEAR).json()["status"] == "Overkill"
    assert send(client, record["id"], model=config.SONNET).json()["status"] == "Overkill"
    client.put("/api/settings", json={"use_recommended": True})
    moved_up = send(client, record["id"], UNCLEAR, model=config.HAIKU).json()
    assert moved_up["status"] == "Upshifted"
    assert moved_up["call"]["model"] == config.SONNET


def test_overuse_math(client, developer):
    _, record = developer
    send(client, record["id"], ROUTINE, config.OPUS)
    send(client, record["id"], ROUTINE, config.HAIKU)
    row = row_for(client, "Ada")
    # 30 input and 60 output: Opus $0.00132, Haiku $0.000033.
    assert row["overspend_usd"] == pytest.approx(0.001287)
    assert row["overuse_percent"] == pytest.approx(0.001287 / 0.001353 * 100)
    assert row["cost_usd"] == pytest.approx(0.001353)
    assert row["tokens"] == 180


def test_calls_below_ideal_are_not_overuse(client, developer):
    _, record = developer
    send(client, record["id"], UNCLEAR, config.HAIKU)
    assert row_for(client, "Ada")["overuse_percent"] == 0


def test_own_tool_calls_are_not_rated(client, developer):
    client.post("/api/simulate-loop")
    assert row_for(client, team.UNATTRIBUTED)["prompts"] == 0


def test_rank_needs_five_rated_prompts_and_lowest_overuse_wins(client, developer):
    _, wasteful = developer
    careful, _ = store.add_developer("Grace")
    newcomer, _ = store.add_developer("Linus")
    for _ in range(config.MIN_RATED_PROMPTS):
        send(client, wasteful["id"], ROUTINE, config.OPUS)
        send(client, careful["id"], ROUTINE, config.HAIKU)
    for _ in range(config.MIN_RATED_PROMPTS - 1):
        send(client, newcomer["id"], ROUTINE, config.HAIKU)

    rows = board(client)
    assert [(r["developer"], r["rank"]) for r in rows] == [
        ("Grace", 1), ("Ada", 2), ("Linus", None),
    ]


def test_a_developer_with_no_calls_is_listed_unranked(client, developer):
    assert board(client)[0]["developer"] == "Ada"
    assert board(client)[0]["rank"] is None


def test_estimated_time_ignores_idle_gaps():
    stamps = [
        "2026-11-06T10:00:00+00:00",
        "2026-11-06T10:04:00+00:00",  # 240 seconds counts.
        "2026-11-06T10:09:01+00:00",  # 301 seconds is idle.
        "2026-11-06T10:09:31+00:00",  # 30 seconds counts.
    ]
    assert team.active_seconds(stamps) == 270
    assert team.active_seconds([]) == 0


def test_time_defaults_to_an_estimate(client, developer):
    _, record = developer
    send(client, record["id"])
    assert row_for(client, "Ada")["dev_time_source"] == "Estimate"


def test_telemetry_replaces_the_estimate_and_adds_up(client, developer):
    auth, record = developer
    send(client, record["id"])
    assert client.post("/v1/metrics", json=metrics(120), headers=auth).status_code == 200
    client.post("/v1/metrics", json=metrics(30), headers=auth)
    row = row_for(client, "Ada")
    assert row["dev_time_source"] == "Measured"
    assert row["dev_seconds"] == 150


def test_telemetry_reads_string_integers_and_gzip(client, developer):
    auth, _ = developer
    payload = metrics()
    point = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]
    point.pop("asDouble")
    point["asInt"] = "45"
    client.post(
        "/v1/metrics",
        content=gzip.compress(json.dumps(payload).encode()),
        headers={**auth, "content-encoding": "gzip"},
    )
    assert row_for(client, "Ada")["dev_seconds"] == 45


def test_telemetry_ignores_other_metrics_and_cumulative_totals(client, developer):
    auth, _ = developer
    client.post("/v1/metrics", json=metrics(10, name="claude_code.commit.count"), headers=auth)
    client.post("/v1/metrics", json=metrics(10, temporality=2), headers=auth)
    assert row_for(client, "Ada")["dev_time_source"] == "Estimate"


def test_telemetry_needs_a_token_and_json(client, developer):
    auth, _ = developer
    assert client.post("/v1/metrics", json=metrics()).status_code == 401
    assert client.post("/v1/metrics", content=b"\x0a\x01", headers=auth).status_code == 415


def test_reset_clears_activity_but_keeps_developers(client, developer):
    auth, record = developer
    send(client, record["id"])
    client.post("/v1/metrics", json=metrics(), headers=auth)
    client.post("/api/reset")
    row = row_for(client, "Ada")
    assert (row["prompts"], row["dev_time_source"]) == (0, "Estimate")
    assert client.get("/api/summary").json()["developers"][0]["name"] == "Ada"


def test_setup_output_has_what_claude_code_needs():
    env = devs.claude_code_settings("cd_token")["env"]
    assert env["ANTHROPIC_AUTH_TOKEN"] == "cd_token"
    assert env["CLAUDE_CODE_GATEWAY_HINT_HEADERS"] == "1"
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json"
    assert env["OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"] == "delta"
    assert "ANTHROPIC_API_KEY" not in env


def test_add_command_prints_the_token_once_and_refuses_duplicates(client, capsys):
    assert devs.add("Grace") == 0
    printed = capsys.readouterr().out
    assert "ANTHROPIC_AUTH_TOKEN" in printed
    token = printed.split('"ANTHROPIC_AUTH_TOKEN": "')[1].split('"')[0]
    assert store.developer_by_token(token)["name"] == "Grace"
    assert devs.add("Grace") == 1


def test_old_databases_are_upgraded_and_keep_their_data(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, source TEXT NOT NULL,
            requested_model TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0, saved_usd REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES ('auto_downshift', '1');
        INSERT INTO calls (ts, source, requested_model, model, cost_usd, status)
        VALUES ('2026-11-05T10:00:00+00:00', 'proxy', 'a', 'a', 0.5, 'OK');
    """)
    old.commit()
    old.close()

    store._db = None
    store.init(path)
    try:
        assert store.get_settings()["use_recommended"] is True
        assert store.list_calls()[0]["ideal_model"] == ""
        assert store.totals()["spent"] == 0.5
        store.init(path)  # Upgrading twice must be harmless.
        assert store.totals()["calls"] == 1
    finally:
        store._db.close()
        store._db = None
