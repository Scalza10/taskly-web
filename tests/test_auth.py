import json

import pytest
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


from taskly.auth import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def fail(client, username="maria"):
    return client.post("/api/login", json={"username": username, "password": "not the password"})


def test_ten_failures_lock_that_username_for_a_while(app, anon, settings):
    add_user(settings, "maria")
    clock = Clock()
    app.state.login_throttle = LoginThrottle(clock)
    for _ in range(10):
        assert fail(anon).status_code == 401
    locked = anon.post("/api/login", json={"username": "maria", "password": PASSWORD})
    assert locked.status_code == 429
    assert 1 <= int(locked.headers["retry-after"]) <= 900
    clock.now += 901
    login(anon, "maria")


def test_the_lock_ignores_the_case_of_the_name(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for name in ["maria", "MARIA"] * 5:
        fail(anon, name)
    assert fail(anon, "Maria").status_code == 429


def test_thirty_failures_from_one_address_lock_every_name(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for i in range(30):
        fail(anon, f"guess{i}")
    assert anon.post("/api/login", json={"username": "maria", "password": PASSWORD}).status_code == 429


def test_a_good_login_clears_that_name_s_failures(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for _ in range(9):
        fail(anon)
    login(anon, "maria")
    for _ in range(9):
        assert fail(anon).status_code == 401


def test_wrong_current_passwords_count_as_failures(app, client):
    app.state.login_throttle = LoginThrottle(Clock())
    for _ in range(10):
        assert client.post("/api/me/password", json={"current": "guess guess", "new": "a brand new one"}).status_code == 403
    response = client.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"})
    assert response.status_code == 429


def test_writes_from_another_site_are_refused(client):
    evil = {"Origin": "https://evil.example"}
    change = {"current": PASSWORD, "new": "a brand new one"}
    response = client.post("/api/me/password", json=change, headers=evil)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/logout", headers=evil).status_code == 403
    assert client.get("/api/me").status_code == 200  # still logged in, password unchanged
    login(client, "maria")


def test_writes_from_the_same_origin_pass_even_with_a_port(app, settings):
    add_user(settings, "maria")
    with TestClient(app, base_url="http://localhost:5173") as client:
        login(client, "maria")
        response = client.post("/api/logout", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 204


def test_parallel_guesses_never_pass_the_limit(app, settings, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    from taskly import users

    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    real = users.authenticate

    def slow(*args):  # as slow as scrypt at full cost, so the guesses overlap
        time.sleep(0.1)
        return real(*args)

    monkeypatch.setattr(users, "authenticate", slow)
    with ThreadPoolExecutor(40) as pool:
        codes = list(pool.map(lambda _: fail(TestClient(app)).status_code, range(40)))
    assert (codes.count(401), codes.count(429)) == (10, 30)


def test_good_logins_never_count_against_the_address(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for _ in range(31):
        login(anon, "maria")
    assert app.state.login_throttle.failures == {}


def test_password_changes_never_count_as_failures(app, client):
    app.state.login_throttle = LoginThrottle(Clock())
    old = PASSWORD
    for i in range(11):
        new = f"a brand new one {i}"
        assert client.post("/api/me/password", json={"current": old, "new": new}).status_code == 204
        old = new
    assert app.state.login_throttle.failures == {}


@pytest.mark.parametrize("name", ["x" * 10_000, "\ud800ab", "has space"], ids=["10k chars", "lone surrogate", "space"])
def test_an_impossible_name_is_a_wrong_login_that_counts_only_against_the_address(app, anon, settings, name):
    add_user(settings, "maria")
    throttle = app.state.login_throttle = LoginThrottle(Clock())
    # Sent as raw JSON: httpx can't encode a lone surrogate, but a browser or script can send "\ud800".
    body = json.dumps({"username": name, "password": "not the password"})
    guess = lambda: anon.post("/api/login", content=body, headers={"Content-Type": "application/json"})
    response = guess()
    assert response.status_code == 401
    assert response.json()["detail"] == "Wrong username or password"
    assert [kind for kind, _ in throttle.failures] == ["ip"]
    for _ in range(29):
        guess()
    assert anon.post("/api/login", json={"username": "maria", "password": PASSWORD}).status_code == 429


def test_passwords_are_bounded(client):
    long = "x" * 1025
    assert client.post("/api/login", json={"username": "maria", "password": long}).status_code == 422
    assert client.post("/api/me/password", json={"current": long, "new": "a brand new one"}).status_code == 422
    assert client.post("/api/me/password", json={"current": PASSWORD, "new": long}).status_code == 422


def test_a_lone_surrogate_in_a_password_is_refused_not_a_crash(client):
    def raw(path, body):  # httpx can't encode a lone surrogate itself
        return client.post(path, content=json.dumps(body), headers={"Content-Type": "application/json"})

    bad = "\ud800" + "abcdefghijk"
    assert raw("/api/login", {"username": "maria", "password": bad}).status_code == 422
    assert raw("/api/me/password", {"current": PASSWORD, "new": bad}).status_code == 422
    assert raw("/api/me/password", {"current": bad, "new": "a brand new one"}).status_code == 422
