"""Per-user budgets on User management, and the shared budget anyone signed in may change."""
from app import config, store

SIMPLE = "Write a commit message for: fix typo in README"


def as_user(token):
    return {"x-cavedawg-token": token}


def run(client, token):
    return client.post(
        "/api/playground", json={"model": config.OPUS, "prompt": SIMPLE}, headers=as_user(token)
    ).json()


def user_row(client, name):
    return next(user for user in client.get("/api/users").json() if user["name"] == name)


def test_users_list_shows_budget_and_spend(client):
    created = client.post(
        "/api/users", json={"name": "Barbara", "team": "Core", "access": "team", "budget_usd": 0.5}
    ).json()["user"]
    assert (created["team"], created["access"], created["budget_usd"]) == ("Core", "team", 0.5)
    _, plain = store.add_developer("Ada", "Core", "self")
    row = user_row(client, "Ada")
    assert row["budget_usd"] == config.DEFAULT_USER_BUDGET_USD and row["spent_usd"] == 0
    run(client, plain)
    assert user_row(client, "Ada")["spent_usd"] > 0


def test_a_user_budget_blocks_only_that_user(client, anthropic):
    _, ada = store.add_developer("Ada", "Core", "self")
    _, grace = store.add_developer("Grace", "Core", "self")
    ada_id = store.developer_by_token(ada)["id"]
    client.patch(f"/api/users/{ada_id}", json={"budget_usd": 0.0000001})
    assert run(client, ada)["status"] != "Blocked by budget"  # spend starts at zero
    blocked = run(client, ada)
    assert blocked["status"] == "Blocked by budget"
    assert "Ada has spent" in blocked["message"]
    assert run(client, grace)["status"] != "Blocked by budget"

    # Clearing the budget with null lifts the limit.
    cleared = client.patch(f"/api/users/{ada_id}", json={"budget_usd": None}).json()
    assert cleared["budget_usd"] is None
    assert run(client, ada)["status"] != "Blocked by budget"


def test_bad_user_budgets_are_refused(client):
    _, ada = store.add_developer("Ada", "Core", "self")
    ada_id = store.developer_by_token(ada)["id"]
    for bad in (-1, -0.01):
        response = client.patch(f"/api/users/{ada_id}", json={"budget_usd": bad})
        assert response.status_code == 400
    assert client.post("/api/users", json={"name": "Bo", "budget_usd": -2}).status_code == 400
    # Other changes leave the budget alone.
    client.patch(f"/api/users/{ada_id}", json={"budget_usd": 2})
    client.patch(f"/api/users/{ada_id}", json={"team": "Kernel"})
    assert user_row(client, "Ada")["budget_usd"] == 2


def test_any_signed_in_user_can_edit_users_and_the_shared_budget(client):
    _, ada = store.add_developer("Ada", "Core", "self")
    ada_id = store.developer_by_token(ada)["id"]
    headers = as_user(ada)
    assert {u["name"] for u in client.get("/api/users", headers=headers).json()} == {"Ada"}
    updated = client.patch(
        f"/api/users/{ada_id}", json={"team": "Ops", "access": "all", "budget_usd": 3},
        headers=headers,
    ).json()
    assert (updated["team"], updated["access"], updated["budget_usd"]) == ("Ops", "all", 3)
    response = client.put("/api/settings", json={"budget_usd": 7}, headers=headers)
    assert response.json()["budget_usd"] == 7


def test_summary_reports_the_server_build(client):
    page = client.get("/")
    assert 'name="cavedawg-build"' in page.text
    assert isinstance(client.get("/api/summary").json()["build"], int)
