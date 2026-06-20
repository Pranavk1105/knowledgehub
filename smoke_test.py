"""
End-to-end smoke test exercising the full API via FastAPI's TestClient.

Runs against the SQLite + in-memory fallbacks, so it needs no external
services. Run with:  python smoke_test.py
"""

import os

# Use a throwaway SQLite file so repeated runs start clean.
os.environ.setdefault("DATABASE_URL", "sqlite:///./smoke.db")
if os.path.exists("smoke.db"):
    os.remove("smoke.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    # 1. Health check shows which backends are active.
    health = client.get("/health").json()
    print("health:", health)

    # 2. Register two users: an author (editor) and a teammate (viewer).
    client.post("/auth/register", json={
        "email": "alice@corp.com", "full_name": "Alice", "password": "secret1", "role": "editor"})
    client.post("/auth/register", json={
        "email": "bob@corp.com", "full_name": "Bob", "password": "secret1", "role": "viewer"})

    alice = client.post("/auth/login", data={"username": "alice@corp.com", "password": "secret1"}).json()["access_token"]
    bob = client.post("/auth/login", data={"username": "bob@corp.com", "password": "secret1"}).json()["access_token"]
    bob_id = client.get("/auth/me", headers=_auth_header(bob)).json()["id"]

    # 3. Alice creates documents.
    docs = [
        {"title": "Kubernetes Production Deployment Guide",
         "content": "How to deploy services to production Kubernetes clusters with rolling updates.",
         "tags": ["devops", "k8s"]},
        {"title": "Disaster Recovery Policy",
         "content": "Backup schedules, RPO/RTO targets and the database restore procedure.",
         "tags": ["policy", "backup"]},
        {"title": "Onboarding FAQ",
         "content": "Frequently asked questions for new engineers joining the platform team.",
         "tags": ["faq", "hr"]},
    ]
    created = []
    for d in docs:
        r = client.post("/documents", json=d, headers=_auth_header(alice))
        assert r.status_code == 201, r.text
        created.append(r.json())
    print("created documents:", [d["title"] for d in created])

    k8s = created[0]

    # 4. Versioning: update the K8s doc and inspect history.
    client.put(f"/documents/{k8s['id']}",
               json={"content": k8s["content"] + " Includes blue-green and canary strategies."},
               headers=_auth_header(alice))
    versions = client.get(f"/documents/{k8s['id']}/versions", headers=_auth_header(alice)).json()
    print("k8s versions:", [v["version"] for v in versions], "(latest first)")
    assert len(versions) == 2

    # 5. Authorization: Bob cannot read the doc until it is shared.
    denied = client.get(f"/documents/{k8s['id']}", headers=_auth_header(bob))
    print("bob read before share -> HTTP", denied.status_code)
    assert denied.status_code == 403

    client.post(f"/documents/{k8s['id']}/share",
                json={"user_id": bob_id, "level": "viewer"}, headers=_auth_header(alice))
    allowed = client.get(f"/documents/{k8s['id']}", headers=_auth_header(bob))
    print("bob read after share  -> HTTP", allowed.status_code)
    assert allowed.status_code == 200

    # 6. Search (permission-filtered). Alice sees all 3; Bob only the shared one.
    alice_hits = client.get("/search", params={"q": "production deployment"}, headers=_auth_header(alice)).json()
    print("alice search 'production deployment':",
          [(h["title"], round(h["score"], 3)) for h in alice_hits["hits"]],
          f"(cached={alice_hits['cached']})")

    bob_hits = client.get("/search", params={"q": "kubernetes"}, headers=_auth_header(bob)).json()
    print("bob search 'kubernetes' (only shared docs):", [h["title"] for h in bob_hits["hits"]])
    assert all(h["document_id"] == k8s["id"] for h in bob_hits["hits"])

    # 7. Cache: a repeated identical query should be served from cache.
    cached_again = client.get("/search", params={"q": "production deployment"}, headers=_auth_header(alice)).json()
    print("alice repeat search cached:", cached_again["cached"])
    assert cached_again["cached"] is True

    # 8. Collaboration: comment + activity feed.
    client.post(f"/documents/{k8s['id']}/comments",
                json={"body": "Should we add a section on Helm?"}, headers=_auth_header(bob))
    feed = client.get(f"/documents/{k8s['id']}/activity", headers=_auth_header(alice)).json()
    print("activity feed actions:", [e["action"] for e in feed])

    print("\nALL CHECKS PASSED ✅")


if __name__ == "__main__":
    main()
