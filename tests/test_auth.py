from fastapi.testclient import TestClient

from conftest import PASSWORD, add_user, login


def test_login_sets_a_safe_cookie(anon, settings):
    add_user(settings, "maria")
    response = login(anon, "maria")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("taskly_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=7776000" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie  # plain http, as on localhost


def test_over_https_the_cookie_is_secure(app, settings):
    add_user(settings, "maria")
    with TestClient(app, base_url="https://testserver") as client:
        assert "Secure" in login(client, "maria").headers["set-cookie"]


def test_me(client):
    assert client.get("/api/me").json() == {"username": "maria"}


def test_login_ignores_the_case_of_the_name(anon, settings):
    add_user(settings, "maria")
    login(anon, "MARIA")
    assert anon.get("/api/me").json() == {"username": "maria"}


def test_wrong_password_or_unknown_user_is_401(anon, settings):
    add_user(settings, "maria")
    for username, password in [("maria", "not the password"), ("nobody", PASSWORD)]:
        response = anon.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 401
        assert response.json()["detail"] == "Wrong username or password"
        assert "set-cookie" not in response.headers


def test_without_login_the_api_is_401_but_health_and_login_are_open(anon):
    assert anon.get("/api/me").status_code == 401
    assert anon.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"}).status_code == 401
    assert anon.get("/health").status_code == 200


def test_logout_ends_the_session(client):
    token = client.cookies.get("taskly_session")
    response = client.post("/api/logout")
    assert response.status_code == 204
    assert 'taskly_session=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]
    client.cookies.set("taskly_session", token)  # even with the old cookie kept
    assert client.get("/api/me").status_code == 401


def test_logout_without_a_session_is_fine(anon):
    assert anon.post("/api/logout").status_code == 204


def test_disabled_user_is_logged_out_at_once(client, conn):
    conn.execute("UPDATE users SET disabled_at = '2026-01-01T00:00:00Z' WHERE username = 'maria'")
    conn.commit()
    assert client.get("/api/me").status_code == 401


def test_the_cookie_is_renewed_when_the_session_is_touched(client, conn):
    assert "set-cookie" not in client.get("/api/me").headers  # used a moment ago
    conn.execute("UPDATE sessions SET last_used_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day')")
    conn.commit()
    response = client.get("/api/me")
    assert response.status_code == 200
    assert "Max-Age=7776000" in response.headers["set-cookie"]


def test_change_password_logs_out_other_devices(app, client, settings):
    with TestClient(app) as phone:
        login(phone, "maria")
        response = client.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"})
        assert response.status_code == 204
        assert phone.get("/api/me").status_code == 401
    assert client.get("/api/me").status_code == 200
    with TestClient(app) as laptop:
        login(laptop, "maria", "a brand new one")


def test_change_password_needs_the_current_one(client):
    response = client.post("/api/me/password", json={"current": "not it at all", "new": "a brand new one"})
    assert response.status_code == 403
    assert response.json()["detail"] == "The current password is wrong"


def test_change_password_refuses_a_short_one(client):
    response = client.post("/api/me/password", json={"current": PASSWORD, "new": "short"})
    assert response.status_code == 422
    assert "at least 10" in response.json()["detail"]


def test_api_answers_are_never_cached(client):
    assert client.get("/api/me").headers["cache-control"] == "no-store"
    assert "cache-control" not in client.get("/health").headers
