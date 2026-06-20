"""Generates demo.ipynb deterministically (stdlib only)."""
import json
import os

def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": list(_lines(lines))}

def code(*lines):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": list(_lines(lines))}

def _lines(lines):
    text = "\n".join(lines)
    out = text.split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]

cells = [
    md("# KnowledgeHub — Indexing & Search Demo",
       "",
       "This notebook demonstrates the **document indexing and keyword-search algorithm** "
       "(Q5) at the heart of KnowledgeHub, then drives the full REST API end-to-end.",
       "",
       "It needs **no external services** — the engine falls back to a pure-Python "
       "inverted index and SQLite, so everything runs in-process.",
       "",
       "**Sections**",
       "1. Tokenization & analysis",
       "2. Building the inverted index",
       "3. TF-IDF + cosine ranking",
       "4. Inspecting the index internals",
       "5. Full API walkthrough (auth → docs → versioning → permissions → search → collaboration)"),

    code("import sys, os",
         "sys.path.insert(0, os.path.abspath('..'))  # import the `app` package",
         "from app.services.inverted_index import InvertedIndex, tokenize, STOP_WORDS"),

    md("## 1. Tokenization & analysis",
       "",
       "Every document and query passes through the same analyzer: lower-case, split on "
       "word boundaries, drop common stop-words. Applying identical analysis to documents "
       "and queries is what makes term matching consistent."),

    code("sample = 'The Kubernetes Production Deployment Guide (v2.0)!'",
         "print('raw     :', sample)",
         "print('tokens  :', tokenize(sample))",
         "print('stopwords removed e.g.:', sorted(list(STOP_WORDS))[:8], '...')"),

    md("## 2. Building the inverted index",
       "",
       "We index a small corpus of knowledge-base articles. Internally the index stores "
       "a **postings map**: `term -> {doc_id: term_frequency}`."),

    code("corpus = {",
         "    'd1': ('Kubernetes Production Deployment Guide',",
         "           'How to deploy services to production Kubernetes clusters with rolling updates and canary releases.'),",
         "    'd2': ('Disaster Recovery Policy',",
         "           'Backup schedules, RPO and RTO targets, and the database restore procedure for production.'),",
         "    'd3': ('Onboarding FAQ',",
         "           'Frequently asked questions for new engineers joining the platform team.'),",
         "    'd4': ('Incident Response Runbook',",
         "           'Steps to triage a production incident, escalate, and run a postmortem.'),",
         "}",
         "",
         "index = InvertedIndex()",
         "for doc_id, (title, body) in corpus.items():",
         "    index.add(doc_id, f'{title} {body}', title=title)",
         "",
         "print('documents indexed:', index.num_docs)",
         "print('unique terms     :', len(index.postings))"),

    md("## 3. TF-IDF + cosine ranking",
       "",
       "At query time each term is weighted by **TF-IDF** and documents are ranked by "
       "**cosine similarity** between the query and document vectors. Cosine normalisation "
       "prevents long documents from dominating purely because they contain more words."),

    code("def show(query):",
         "    print(f'\\nQuery: {query!r}')",
         "    results = index.search(query)",
         "    if not results:",
         "        print('  (no matches)')",
         "    for doc_id, score, snippet in results:",
         "        print(f'  {score:.4f}  {index.title_of(doc_id):38}  {snippet}')",
         "",
         "show('production deployment')",
         "show('database backup recovery')",
         "show('incident postmortem')",
         "show('vacation policy')  # no relevant doc"),

    md("## 4. Inspecting the index internals",
       "",
       "We can look directly at the postings list and the computed IDF weights to see "
       "*why* a document ranks where it does. Rarer terms carry more weight."),

    code("term = 'production'",
         "print(f'postings for {term!r}:', dict(index.postings[term]))",
         "print(f'IDF({term!r})      = {index._idf(term):.4f}')",
         "print(f'IDF(\\'kubernetes\\') = {index._idf(\"kubernetes\"):.4f}  # rarer -> higher weight')"),

    md("## 5. Full API walkthrough",
       "",
       "Now the same indexing logic running behind the **FastAPI** service, exercised with "
       "`TestClient` (no server process needed). This mirrors `smoke_test.py`."),

    code("os.environ['DATABASE_URL'] = 'sqlite:///./demo_nb.db'",
         "if os.path.exists('demo_nb.db'):",
         "    os.remove('demo_nb.db')",
         "from fastapi.testclient import TestClient",
         "from app.main import app",
         "client = TestClient(app)",
         "client.get('/health').json()"),

    code("# Register an author and a teammate",
         "client.post('/auth/register', json={'email':'alice@corp.com','full_name':'Alice','password':'secret1','role':'editor'})",
         "client.post('/auth/register', json={'email':'bob@corp.com','full_name':'Bob','password':'secret1','role':'viewer'})",
         "alice = client.post('/auth/login', data={'username':'alice@corp.com','password':'secret1'}).json()['access_token']",
         "bob   = client.post('/auth/login', data={'username':'bob@corp.com','password':'secret1'}).json()['access_token']",
         "A = {'Authorization': f'Bearer {alice}'}",
         "B = {'Authorization': f'Bearer {bob}'}",
         "bob_id = client.get('/auth/me', headers=B).json()['id']",
         "print('logged in as alice & bob')"),

    code("# Alice creates documents",
         "for title, content, tags in [",
         "    ('Kubernetes Production Deployment Guide','Deploy services to production Kubernetes clusters with rolling updates.',['devops']),",
         "    ('Disaster Recovery Policy','Backup schedules, RPO/RTO targets and the database restore procedure.',['policy']),",
         "    ('Onboarding FAQ','Frequently asked questions for new engineers.',['hr']),",
         "]:",
         "    client.post('/documents', json={'title':title,'content':content,'tags':tags}, headers=A)",
         "doc = client.get('/search', params={'q':'kubernetes'}, headers=A).json()['hits'][0]",
         "doc_id = doc['document_id']",
         "print('created; top hit for kubernetes:', doc['title'])"),

    code("# Versioning: edit creates a new immutable revision",
         "client.put(f'/documents/{doc_id}', json={'content':'Updated: adds blue-green and canary strategies.'}, headers=A)",
         "versions = client.get(f'/documents/{doc_id}/versions', headers=A).json()",
         "print('versions (latest first):', [v['version'] for v in versions])"),

    code("# Authorization: Bob is blocked until the doc is shared with him",
         "print('bob before share ->', client.get(f'/documents/{doc_id}', headers=B).status_code)",
         "client.post(f'/documents/{doc_id}/share', json={'user_id':bob_id,'level':'viewer'}, headers=A)",
         "print('bob after  share ->', client.get(f'/documents/{doc_id}', headers=B).status_code)"),

    code("# Permission-filtered search: Bob only sees what he can access",
         "print('alice sees:', [h['title'] for h in client.get('/search', params={'q':'guide policy faq'}, headers=A).json()['hits']])",
         "print('bob   sees:', [h['title'] for h in client.get('/search', params={'q':'guide policy faq'}, headers=B).json()['hits']])"),

    code("# Caching: identical repeated query is served from cache",
         "r1 = client.get('/search', params={'q':'production'}, headers=A).json()",
         "r2 = client.get('/search', params={'q':'production'}, headers=A).json()",
         "print('first call cached:', r1['cached'], '| second call cached:', r2['cached'])"),

    code("# Collaboration: comment + activity feed",
         "client.post(f'/documents/{doc_id}/comments', json={'body':'Should we add a Helm section?'}, headers=B)",
         "feed = client.get(f'/documents/{doc_id}/activity', headers=A).json()",
         "for e in feed:",
         "    print(f\"  {e['action']:10} {e['detail']}\")"),

    md("## Summary",
       "",
       "We demonstrated the full lifecycle: **tokenize → index → TF-IDF/cosine rank**, then "
       "the same engine behind a secured API with versioning, per-document permissions, "
       "permission-filtered + cached search, and collaboration logging — the core of the "
       "KnowledgeHub design."),
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = os.path.join(os.path.dirname(__file__), "demo.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1)
print("wrote", out)
