"""API tests — auth, generation, gallery, ownership, validation."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_register_returns_token(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "a@b.pk", "display_name": "Ab", "password": "password123"},
    )
    assert resp.status_code == 201
    assert resp.json()["access_token"]
    assert resp.json()["token_type"] == "bearer"


def test_register_duplicate_email_conflicts(client):
    payload = {"email": "dup@b.pk", "display_name": "Dup", "password": "password123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_register_rejects_short_password(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "s@b.pk", "display_name": "S", "password": "short"},
    )
    assert resp.status_code == 422


def test_login_wrong_password_is_401(client):
    client.post(
        "/api/auth/register",
        json={"email": "l@b.pk", "display_name": "L", "password": "password123"},
    )
    resp = client.post("/api/auth/login", json={"email": "l@b.pk", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_unknown_email_is_401(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@b.pk", "password": "password123"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_user(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "tester@rang.pk"


def test_generate_requires_auth(client):
    resp = client.post("/api/generate", json={"prompt": "a mountain"})
    assert resp.status_code == 401


def test_generate_creates_image(auth_client):
    resp = auth_client.post(
        "/api/generate",
        json={"prompt": "a mountain at sunset", "style": "cinematic", "aspect_ratio": "16:9"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["width"] == 1024
    assert body["height"] == 576
    assert body["image_url"] == f"/api/images/{body['id']}"
    assert body["provider"] == "local"


def test_generate_rejects_blank_prompt(auth_client):
    resp = auth_client.post("/api/generate", json={"prompt": "   "})
    assert resp.status_code == 422


def test_generate_rejects_overlong_prompt(auth_client):
    resp = auth_client.post("/api/generate", json={"prompt": "x" * 900})
    assert resp.status_code == 422


def test_generate_rejects_bad_ratio(auth_client):
    resp = auth_client.post("/api/generate", json={"prompt": "a forest", "aspect_ratio": "7:3"})
    assert resp.status_code == 422


def test_image_endpoint_serves_png(auth_client):
    gen = auth_client.post("/api/generate", json={"prompt": "a forest"}).json()
    resp = auth_client.get(gen["image_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumb_endpoint_serves_png(auth_client):
    gen = auth_client.post("/api/generate", json={"prompt": "a forest"}).json()
    resp = auth_client.get(gen["thumb_url"])
    assert resp.status_code == 200
    assert resp.content[:4] == b"\x89PNG"


def test_missing_image_is_404(auth_client):
    assert auth_client.get("/api/images/99999").status_code == 404


def test_gallery_lists_own_generations(auth_client):
    for p in ("a mountain", "a city", "an ocean"):
        auth_client.post("/api/generate", json={"prompt": p})
    resp = auth_client.get("/api/generations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_gallery_pagination(auth_client):
    for i in range(5):
        auth_client.post("/api/generate", json={"prompt": f"scene number {i}"})
    page = auth_client.get("/api/generations?limit=2&offset=0").json()
    assert len(page["items"]) == 2
    assert page["total"] == 5
    page2 = auth_client.get("/api/generations?limit=2&offset=2").json()
    assert len(page2["items"]) == 2
    assert page["items"][0]["id"] != page2["items"][0]["id"]


def test_gallery_search_filters(auth_client):
    auth_client.post("/api/generate", json={"prompt": "a mountain at dawn"})
    auth_client.post("/api/generate", json={"prompt": "a city at night"})
    resp = auth_client.get("/api/generations?q=mountain")
    assert resp.json()["total"] == 1


def test_favourite_toggle(auth_client):
    gen = auth_client.post("/api/generate", json={"prompt": "a forest"}).json()
    resp = auth_client.patch(f"/api/generations/{gen['id']}/favourite", json={"is_favourite": True})
    assert resp.status_code == 200
    assert resp.json()["is_favourite"] is True

    favs = auth_client.get("/api/generations?favourite_only=true").json()
    assert favs["total"] == 1


def test_delete_generation(auth_client):
    gen = auth_client.post("/api/generate", json={"prompt": "a forest"}).json()
    assert auth_client.delete(f"/api/generations/{gen['id']}").status_code == 204
    assert auth_client.get(f"/api/generations/{gen['id']}").status_code == 404


def test_other_users_generation_is_404(client):
    """Ownership is enforced, and we return 404 rather than 403."""
    first = client.post(
        "/api/auth/register",
        json={"email": "one@b.pk", "display_name": "One", "password": "password123"},
    ).json()
    client.headers.update({"Authorization": f"Bearer {first['access_token']}"})
    gen = client.post("/api/generate", json={"prompt": "a forest"}).json()

    second = client.post(
        "/api/auth/register",
        json={"email": "two@b.pk", "display_name": "Two", "password": "password123"},
    ).json()
    client.headers.update({"Authorization": f"Bearer {second['access_token']}"})

    assert client.get(f"/api/generations/{gen['id']}").status_code == 404
    assert client.delete(f"/api/generations/{gen['id']}").status_code == 404


def test_preview_returns_parsed_spec(auth_client):
    resp = auth_client.post("/api/preview", json={"prompt": "a neon city at sunset"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "city"
    assert body["style"] == "neon"
    assert body["size"] == "1024x1024"


def test_providers_endpoint(auth_client):
    resp = auth_client.get("/api/providers")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"local", "gemini"}
    local = next(p for p in resp.json() if p["name"] == "local")
    assert local["available"] is True


def test_unknown_api_path_returns_json_404(auth_client):
    resp = auth_client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
