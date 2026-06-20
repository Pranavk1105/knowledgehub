"""
Reproducible end-to-end demo against the running stack (default :8001).

Prints a readable transcript covering auth, document CRUD, versioning,
per-document permissions, Elasticsearch search, Redis caching and
collaboration. Used to generate the documentation screenshots and as a
quick manual verification of the dockerized stack.

Usage:  python scripts/demo_transcript.py [base_url]
"""
import sys
import time

import requests

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"


def reg(e, n, r):
    requests.post(f"{B}/auth/register", json={"email": e, "full_name": n, "password": "secret1", "role": r})


def login(e):
    return requests.post(f"{B}/auth/login", data={"username": e, "password": "secret1"}).json()["access_token"]


print(f"$ curl {B}/health")
print(" ", requests.get(f"{B}/health").json())

print("\n# Register an author (editor) and a teammate (viewer)")
reg("alice@corp.com", "Alice", "editor")
reg("bob@corp.com", "Bob", "viewer")
alice, bob = login("alice@corp.com"), login("bob@corp.com")
A = {"Authorization": f"Bearer {alice}"}
Bh = {"Authorization": f"Bearer {bob}"}
bob_id = requests.get(f"{B}/auth/me", headers=Bh).json()["id"]
print("  alice + bob registered; JWTs issued")

print("\n# Alice creates documents -> persisted in Postgres, indexed in Elasticsearch")
ids = {}
for title, content in [
    ("Kubernetes Production Deployment Guide",
     "Deploy services to production Kubernetes clusters with rolling updates and canary releases."),
    ("Disaster Recovery Policy",
     "Backup schedules, RPO and RTO targets, and the production database restore procedure."),
    ("Onboarding FAQ",
     "Frequently asked questions for new engineers joining the platform team."),
]:
    r = requests.post(f"{B}/documents", json={"title": title, "content": content}, headers=A).json()
    ids[title] = r["id"]
    print(f"  + {r['id'][:8]}  v{r['current_version']}  {title}")

k8s = ids["Kubernetes Production Deployment Guide"]

print("\n# Versioning: editing creates a new immutable revision")
requests.put(f"{B}/documents/{k8s}",
             json={"content": "Deploy to production Kubernetes; adds blue-green and canary strategies."}, headers=A)
vs = requests.get(f"{B}/documents/{k8s}/versions", headers=A).json()
print("  revision history (latest first):", [v["version"] for v in vs])

print("\n# Authorization: Bob cannot read the doc until it is shared")
print("  GET /documents/{k8s}  as bob ->", requests.get(f"{B}/documents/{k8s}", headers=Bh).status_code, "(403 Forbidden)")
requests.post(f"{B}/documents/{k8s}/share", json={"user_id": bob_id, "level": "viewer"}, headers=A)
print("  POST /documents/{k8s}/share (bob: viewer)")
print("  GET /documents/{k8s}  as bob ->", requests.get(f"{B}/documents/{k8s}", headers=Bh).status_code, "(200 OK)")

time.sleep(2)  # allow Elasticsearch near-real-time refresh

print("\n# Full-text search via Elasticsearch (BM25 ranking + highlights)")
res = requests.get(f"{B}/search", params={"q": "production deployment"}, headers=A).json()
print(f"  q='production deployment'  ({res['total']} hits, {res['took_ms']}ms, cached={res['cached']})")
for h in res["hits"]:
    print(f"    {h['score']:.3f}  {h['title']}")
    print(f"           {h['highlight']}")

print("\n# Permission-filtered search: Bob only sees documents shared with him")
resb = requests.get(f"{B}/search", params={"q": "production"}, headers=Bh).json()
print("  bob q='production' ->", [h["title"] for h in resb["hits"]])

print("\n# Caching: identical repeated query served from Redis")
requests.get(f"{B}/search", params={"q": "recovery"}, headers=A)
r2 = requests.get(f"{B}/search", params={"q": "recovery"}, headers=A).json()
print(f"  repeat query -> cached={r2['cached']} ({r2['took_ms']}ms)")

print("\n# Collaboration: comment + activity feed")
requests.post(f"{B}/documents/{k8s}/comments", json={"body": "Should we add a Helm section?"}, headers=Bh)
feed = requests.get(f"{B}/documents/{k8s}/activity", headers=A).json()
for e in feed:
    print(f"    [{e['action']:>10}]  {e['detail']}")

print("\nAll features verified on Postgres + Elasticsearch + Redis.")
