import re


def test_page_and_scripts_are_never_served_stale(client):
    page = client.get("/")
    assert page.headers["cache-control"] == "no-cache"
    # The script and stylesheet URLs carry a version, so an edge cache can't hand back an old copy.
    script = re.search(r'src="(/static/app\.js\?v=\d+)"', page.text).group(1)
    assert re.search(r'href="/static/style\.css\?v=\d+"', page.text)
    assert client.get(script).headers["cache-control"] == "no-cache"


def test_simulated_switch_turns_off_for_anyone_signed_in(client, developer):
    client.put("/api/settings", json={"simulated": True})
    auth, _ = developer
    token = auth["authorization"].removeprefix("Bearer ")
    response = client.put(
        "/api/settings", json={"simulated": False}, headers={"x-cavedawg-token": token}
    )
    assert response.status_code == 200
    assert response.json()["simulated"] is False
