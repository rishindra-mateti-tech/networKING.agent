"""
Cross-tenant isolation and authentication.

This app is multi-tenant, so the failure that matters most is one account
reaching another account's data. Every id-addressed endpoint is exercised
by a second user against the first user's resources; anything other than a
refusal is a data leak.
"""
from _harness import Results, client, make_user

r = Results()


def run():
    a_headers, a_email = make_user("tenant_a")
    b_headers, _ = make_user("tenant_b")

    created = client.post(
        "/api/connections",
        headers=a_headers,
        json={
            "name": "A Private Contact",
            "company": "ACorp",
            "current_title": "CTO",
            "profile_url": "https://linkedin.com/in/a-private-contact",
        },
    )
    assert created.status_code == 200, created.text
    conn_id = created.json()["id"]

    key = client.post(
        "/api/keys",
        headers=a_headers,
        json={"key_value": "A-private-key-value", "role": "primary", "label": "A key"},
    )
    assert key.status_code == 200, key.text
    key_id = key.json()["id"]

    client.post(
        "/api/settings/batch",
        headers=a_headers,
        json={"settings": [{"key": "tone_examples", "value": "A private tone"}]},
    )
    log = client.post(
        f"/api/connections/{conn_id}/logs",
        headers=a_headers,
        json={"message": "A private log", "sender": "user"},
    )
    log_id = log.json().get("id") if log.status_code == 200 else 1

    # ---- reads ----
    got = client.get(f"/api/connections/{conn_id}", headers=b_headers)
    r.check("read another tenant's connection", got.status_code == 404, f"status {got.status_code}")

    listed = client.get("/api/connections", headers=b_headers)
    r.check(
        "connection list stays scoped to the caller",
        listed.status_code == 200 and all(c["id"] != conn_id for c in listed.json()),
        "another tenant's connection appeared in the list",
    )

    logs = client.get(f"/api/connections/{conn_id}/logs", headers=b_headers)
    r.check(
        "read another tenant's logs",
        logs.status_code == 404 or (logs.status_code == 200 and logs.json() == []),
        f"status {logs.status_code} body {logs.text[:120]}",
    )

    # Uploaded screenshots are reachable only through this endpoint now, so it
    # carries the isolation the removed static mount never had.
    shot = client.get(f"/api/connections/{conn_id}/logs/{log_id}/screenshot", headers=b_headers)
    r.check(
        "read another tenant's log screenshot",
        shot.status_code == 404,
        f"status {shot.status_code}",
    )
    own_shot = client.get(f"/api/connections/{conn_id}/logs/{log_id}/screenshot", headers=a_headers)
    r.check(
        "own log with no screenshot is a 404, not a server error",
        own_shot.status_code == 404,
        f"status {own_shot.status_code}",
    )
    anon_shot = client.get(f"/api/connections/{conn_id}/logs/{log_id}/screenshot")
    r.check(
        "log screenshot needs authentication",
        anon_shot.status_code in (401, 403),
        f"status {anon_shot.status_code}",
    )

    keys = client.get("/api/keys", headers=b_headers)
    r.check(
        "key list stays scoped to the caller",
        keys.status_code == 200 and all(k["id"] != key_id for k in keys.json()),
        "another tenant's key appeared in the list",
    )

    settings = client.get("/api/settings", headers=b_headers)
    tone = {s["key"]: s["value"] for s in settings.json()}.get("tone_examples")
    r.check("settings stay scoped to the caller", tone != "A private tone", f"leaked tone {tone!r}")

    # ---- writes ----
    write_attempts = [
        ("change status", client.put, f"/api/connections/{conn_id}/status", {"status": "sent"}),
        ("toggle star", client.put, f"/api/connections/{conn_id}/star", None),
        ("select variant", client.put, f"/api/connections/{conn_id}/select-variant", {"variant": "referral"}),
        ("append log", client.post, f"/api/connections/{conn_id}/logs", {"message": "injected", "sender": "user"}),
        ("toggle key", client.put, f"/api/keys/{key_id}/toggle", None),
        ("test key", client.post, f"/api/keys/{key_id}/test", None),
        ("generate email", client.post, f"/api/connections/{conn_id}/generate-email", None),
    ]
    for label, method, path, body in write_attempts:
        resp = method(path, headers=b_headers, json=body) if body is not None else method(path, headers=b_headers)
        r.check(f"write to another tenant: {label}", resp.status_code in (404, 422), f"status {resp.status_code}")

    # ---- deletes ----
    r.check(
        "delete another tenant's key",
        client.delete(f"/api/keys/{key_id}", headers=b_headers).status_code == 404,
        "delete was not refused",
    )
    r.check(
        "delete another tenant's connection",
        client.delete(f"/api/connections/{conn_id}", headers=b_headers).status_code == 404,
        "delete was not refused",
    )

    # ---- owner's data survived intact ----
    after = client.get(f"/api/connections/{conn_id}", headers=a_headers)
    r.check("owner's connection still exists", after.status_code == 200, f"status {after.status_code}")
    if after.status_code == 200:
        r.check("owner's connection was not modified", after.json()["status"] != "sent",
                f"status became {after.json()['status']}")
    r.check(
        "owner's key still exists",
        any(k["id"] == key_id for k in client.get("/api/keys", headers=a_headers).json()),
        "key was deleted by another tenant",
    )

    # ---- unauthenticated access ----
    unauthenticated = [
        ("GET", "/api/connections", None),
        ("GET", f"/api/connections/{conn_id}", None),
        ("GET", "/api/keys", None),
        ("GET", "/api/settings", None),
        ("GET", "/api/analytics/overview", None),
        ("GET", "/api/auth/me", None),
        ("POST", "/api/settings/batch", {"settings": []}),
        ("DELETE", f"/api/connections/{conn_id}", None),
    ]
    for method, path, body in unauthenticated:
        resp = client.request(method, path, json=body)
        r.check(f"unauthenticated {method} {path}", resp.status_code in (401, 403), f"status {resp.status_code}")

    forged = client.get("/api/connections", headers={"Authorization": "Bearer not.a.real.token"})
    r.check("forged token rejected", forged.status_code in (401, 403), f"status {forged.status_code}")

    # ---- uploaded files are not served over HTTP at all ----
    # /uploads was once a public StaticFiles mount, which handed every account's
    # profile and conversation screenshots to anyone with a filename. Nothing
    # fetches them over HTTP -- agents open them by path server-side -- so the
    # route should simply not exist.
    for path in ("/uploads/", "/uploads/anything.png"):
        resp = client.get(path)
        r.check(
            f"uploaded files not publicly served: {path}",
            resp.status_code == 404,
            f"status {resp.status_code}",
        )

    # ---- account rules ----
    dup = client.post("/api/auth/register", json={"email": a_email, "password": "otherpass"})
    r.check("duplicate email registration refused", dup.status_code == 400, f"status {dup.status_code}")

    wrong = client.post("/api/auth/login", json={"email": a_email, "password": "wrongpassword"})
    r.check("wrong password refused", wrong.status_code == 401, f"status {wrong.status_code}")

    return r.report("cross-tenant isolation and auth")


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
