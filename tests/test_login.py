"""Username and password login, the Demo signup button, and admin password management."""
from app import config, store

GOOD = "correct horse"


def page(token):
    return {"x-cavedawg-token": token}


def signup(client, name="Dana", password=GOOD):
    return client.post("/api/signup", json={"name": name, "password": password})


def test_demo_signup_creates_a_login_and_a_token(client):
    response = signup(client).json()
    assert response["user"]["name"] == "Dana"
    assert response["user"]["team"] == config.DEMO_TEAM
    assert response["user"]["access"] == "self"
    assert response["user"]["has_password"] is True
    assert response["viewer"]["name"] == "Dana"
    # The session signs in to the page, and the token works for Claude Code.
    assert client.get("/api/me", headers=page(response["session"])).json()["name"] == "Dana"
    assert response["token"].startswith("cd_")
    assert response["claude_code_settings"]["env"]["ANTHROPIC_AUTH_TOKEN"] == response["token"]


def test_demo_signup_follows_the_configured_access(client, monkeypatch):
    monkeypatch.setattr(config.settings, "demo_access", "team")
    assert signup(client).json()["user"]["access"] == "team"
    monkeypatch.setattr(config.settings, "demo_access", "off")
    assert client.get("/api/signin-options").json() == {"demo": False, "demo_access": None}
    assert signup(client, "Eve").status_code == 403


def test_signup_refuses_taken_names_and_short_passwords(client):
    signup(client)
    assert signup(client).json()["error"] == "Dana is taken. Choose another username."
    assert signup(client, "Eve", "short").status_code == 400
    assert signup(client, "  ", GOOD).status_code == 400


def test_login_with_username_and_password(client):
    signup(client)
    session = client.post("/api/login", json={"name": "Dana", "password": GOOD}).json()["session"]
    assert client.get("/api/me", headers=page(session)).json()["name"] == "Dana"


def test_wrong_password_and_unknown_user_look_the_same(client):
    signup(client)
    wrong = client.post("/api/login", json={"name": "Dana", "password": "nope nope"})
    unknown = client.post("/api/login", json={"name": "Nobody", "password": GOOD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"error": "Wrong username or password."}


def test_token_only_users_cannot_log_in_with_a_password(client):
    store.add_developer("Ada")
    assert client.post("/api/login", json={"name": "Ada", "password": ""}).status_code == 401


def test_logout_ends_only_that_session(client):
    signup(client)
    first = client.post("/api/login", json={"name": "Dana", "password": GOOD}).json()["session"]
    second = client.post("/api/login", json={"name": "Dana", "password": GOOD}).json()["session"]
    client.post("/api/logout", headers=page(first))
    assert client.get("/api/me", headers=page(first)).status_code == 401
    assert client.get("/api/me", headers=page(second)).status_code == 200


def test_sessions_cannot_spend_through_the_proxy(client):
    session = signup(client).json()["session"]
    response = client.post(
        "/v1/messages",
        json={"model": config.HAIKU, "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
        headers={"authorization": f"Bearer {session}"},
    )
    assert response.status_code == 401


def test_admin_sets_a_password_and_old_sessions_end(client):
    created = signup(client).json()
    user_id = created["user"]["id"]
    updated = client.patch(f"/api/users/{user_id}", json={"password": "a brand new one"}).json()
    assert updated["has_password"] is True
    assert client.get("/api/me", headers=page(created["session"])).status_code == 401
    assert client.post("/api/login", json={"name": "Dana", "password": GOOD}).status_code == 401
    assert client.post(
        "/api/login", json={"name": "Dana", "password": "a brand new one"}
    ).status_code == 200
    assert client.patch(f"/api/users/{user_id}", json={"password": "short"}).status_code == 400


def test_admin_can_create_a_user_with_a_password(client):
    created = client.post(
        "/api/users", json={"name": "Grace", "team": "Core", "access": "team", "password": GOOD}
    ).json()
    assert created["user"]["has_password"] is True
    assert client.post("/api/login", json={"name": "Grace", "password": GOOD}).status_code == 200


def test_users_cannot_change_passwords_without_all_access(client):
    session = signup(client).json()["session"]
    user_id = store.list_developers()[0]["id"]
    response = client.patch(
        f"/api/users/{user_id}", json={"password": "my own idea"}, headers=page(session)
    )
    assert response.status_code == 403


def test_passwords_are_never_returned_or_stored_plain(client):
    created = signup(client).json()
    assert "password" not in created["user"] and "password_hash" not in created["user"]
    stored = store.get_developer(created["user"]["id"])["password_hash"]
    assert stored.startswith("scrypt$") and GOOD not in stored
    assert all("password_hash" not in user for user in client.get("/api/users").json())
