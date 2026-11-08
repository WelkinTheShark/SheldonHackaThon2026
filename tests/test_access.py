"""Sign-in, per-token viewing access, user management and shared roasts."""
from app import config, store

SIMPLE = "Write a commit message for: fix typo in README"


def as_user(token):
    return {"x-cavedawg-token": token}


def send(client, token, prompt=SIMPLE, model=config.OPUS):
    return client.post(
        "/api/playground", json={"model": model, "prompt": prompt}, headers=as_user(token)
    ).json()


def names_in_history(client, token):
    return {row["developer"] for row in client.get("/api/history", headers=as_user(token)).json()}


def team_setup():
    _, ada = store.add_developer("Ada", "Core", "self")
    _, grace = store.add_developer("Grace", "Core", "team")
    _, linus = store.add_developer("Linus", "Kernel", "all")
    _, ken = store.add_developer("Ken", "Kernel", "self")
    return ada, grace, linus, ken


def test_page_api_needs_a_token(client):
    for path in ("/api/summary", "/api/history", "/api/roasts", "/api/me"):
        response = client.get(path, headers=as_user("wrong"))
        assert response.status_code == 401
        assert response.json() == {"error": "Sign in to CaveDawg."}
    assert client.get("/api/hello").status_code == 200


def test_gateway_token_signs_in_as_admin(client):
    me = client.get("/api/me").json()
    assert (me["name"], me["access"], me["can_manage"]) == ("Admin", "all", True)


def test_self_team_and_all_access_see_different_calls(client):
    ada, grace, linus, ken = team_setup()
    for token in (ada, grace, linus, ken):
        send(client, token)

    assert names_in_history(client, ada) == {"Ada"}
    assert names_in_history(client, grace) == {"Ada", "Grace"}
    assert names_in_history(client, linus) == {"Ada", "Grace", "Linus", "Ken"}
    assert names_in_history(client, ken) == {"Ken"}
    board = client.get("/api/leaderboard", headers=as_user(grace)).json()["rows"]
    assert {row["developer"] for row in board} == {"Ada", "Grace"}


def test_calls_are_sent_as_the_signed_in_user(client):
    ada, *_ = team_setup()
    linus_id = store.list_developers()[2]["id"]
    row = client.post(
        "/api/playground",
        json={"model": config.OPUS, "prompt": SIMPLE, "developer_id": linus_id},
        headers=as_user(ada),
    ).json()["call"]
    assert row["developer_id"] == store.developer_by_token(ada)["id"]


def test_only_all_access_can_manage(client):
    ada, grace, linus, _ = team_setup()
    for token in (ada, grace):
        headers = as_user(token)
        # The shared budget is open to anyone signed in for the demo. Routing is not.
        assert client.put("/api/settings", json={"budget_usd": 9}, headers=headers).status_code == 200
        assert client.put("/api/settings", json={"level": 3}, headers=headers).status_code == 403
        assert client.put("/api/settings", json={"use_recommended": True}, headers=headers).status_code == 403
        assert client.post("/api/reset", headers=headers).status_code == 403
        # User management is open to anyone signed in, for the demo.
        assert client.get("/api/users", headers=headers).status_code == 200
    assert client.get("/api/users", headers=as_user(linus)).status_code == 200
    assert client.get("/api/users", headers={"x-cavedawg-token": ""}).status_code == 401


def test_create_user_issues_a_working_token(client, anthropic):
    created = client.post(
        "/api/users", json={"name": "Barbara", "team": "Core", "access": "team"}
    ).json()
    assert created["user"]["team"] == "Core" and created["user"]["access"] == "team"
    token = created["token"]
    assert created["claude_code_settings"]["env"]["ANTHROPIC_AUTH_TOKEN"] == token

    proxied = client.post(
        "/v1/messages",
        json={"model": config.HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]},
        headers={"authorization": f"Bearer {token}"},
    )
    assert proxied.status_code == 200
    assert client.get("/api/me", headers=as_user(token)).json()["name"] == "Barbara"


def test_duplicate_and_bad_users_are_refused(client):
    client.post("/api/users", json={"name": "Ada"})
    assert client.post("/api/users", json={"name": "Ada"}).json()["error"] == "Ada already exists."
    assert client.post("/api/users", json={"name": "  "}).status_code == 400
    assert client.post("/api/users", json={"name": "Bo", "access": "root"}).status_code == 400


def test_update_access_and_team(client):
    ada, *_ = team_setup()
    ada_id = store.developer_by_token(ada)["id"]
    updated = client.patch(f"/api/users/{ada_id}", json={"team": "Kernel", "access": "team"}).json()
    assert (updated["team"], updated["access"]) == ("Kernel", "team")
    send(client, ada)
    assert names_in_history(client, ada) == {"Ada"}  # Kernel teammates have sent nothing yet


def test_new_token_replaces_the_old_one(client):
    ada, *_ = team_setup()
    ada_id = store.developer_by_token(ada)["id"]
    fresh = client.post(f"/api/users/{ada_id}/token").json()["token"]
    assert client.get("/api/me", headers=as_user(ada)).status_code == 401
    assert client.get("/api/me", headers=as_user(fresh)).json()["name"] == "Ada"


def test_roast_then_unchanged_send_shares_the_roast_with_the_call(client):
    ada, grace, *_ = team_setup()
    roast = client.post("/api/roast", json={"text": SIMPLE}, headers=as_user(ada)).json()
    send(client, ada)
    send(client, ada, prompt=SIMPLE + " please")

    rows = client.get("/api/history", headers=as_user(grace)).json()
    by_prompt = {row["prompt"]: row for row in rows}
    assert by_prompt[SIMPLE]["roast"]["id"] == roast["id"]
    assert by_prompt[SIMPLE + " please"]["roast"] is None
    shared = client.get("/api/roasts", headers=as_user(grace)).json()
    assert [row["id"] for row in shared] == [roast["id"]]
    assert shared[0]["developer"] == "Ada"


def test_roasts_follow_viewing_access(client):
    ada, _, _, ken = team_setup()
    client.post("/api/roast", json={"text": "Design the cache layer"}, headers=as_user(ada))
    assert client.get("/api/roasts", headers=as_user(ken)).json() == []
    assert len(client.get("/api/roasts").json()) == 1


def test_roast_an_existing_call(client):
    ada, _, _, ken = team_setup()
    call_id = send(client, ada)["call"]["id"]
    roasted = client.post(f"/api/calls/{call_id}/roast", headers=as_user(ada)).json()
    assert roasted["prompt"] == SIMPLE and roasted["receipt"]["model"] == "Haiku 5.5"
    assert client.get("/api/history", headers=as_user(ada)).json()[0]["roast"]["id"] == roasted["id"]
    # Someone who can't see the call can't roast it.
    assert client.post(f"/api/calls/{call_id}/roast", headers=as_user(ken)).status_code == 404


def test_simulated_roast_says_so(client):
    client.put("/api/settings", json={"simulated": True})
    roasted = client.post("/api/roast", json={"text": SIMPLE}).json()
    assert roasted["simulated"] is True
    assert "Simulated" in roasted["receipt"]["note"]
    client.put("/api/settings", json={"simulated": False})
    assert client.post("/api/roast", json={"text": SIMPLE}).json()["simulated"] is False


def test_anyone_signed_in_can_turn_off_simulated_responses(client):
    ada, *_ = team_setup()
    client.put("/api/settings", json={"simulated": True})
    response = client.put("/api/settings", json={"simulated": False}, headers=as_user(ada))
    assert response.status_code == 200 and response.json()["simulated"] is False
    both = {"simulated": True, "use_recommended": True}
    assert client.put("/api/settings", json=both, headers=as_user(ada)).status_code == 403


def test_playground_defaults_to_opus(client, anthropic):
    client.post("/api/playground", json={"prompt": SIMPLE})
    assert anthropic.models == [config.OPUS]
