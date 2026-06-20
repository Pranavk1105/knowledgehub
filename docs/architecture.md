# KnowledgeHub — System Architecture

## High-level component diagram

```mermaid
flowchart TB
    subgraph Clients
        WEB["Web App"]
        MOB["Mobile App"]
    end

    LB["Load Balancer / API Gateway<br/>(TLS, rate limiting)"]

    subgraph API["KnowledgeHub API (stateless, horizontally scaled)"]
        AUTH["Auth Service<br/>JWT, RBAC, per-doc ACL"]
        DOCS["Document Service<br/>CRUD + versioning"]
        SEARCHSVC["Search Service<br/>query + permission filter"]
        COLLAB["Collaboration Service<br/>comments, activity feed"]
        IDX["Indexing Pipeline<br/>sync docs -> search"]
    end

    subgraph Data["Data & Infrastructure"]
        PG[("PostgreSQL<br/>documents, versions,<br/>permissions, logs")]
        ES[("Elasticsearch<br/>full-text inverted index")]
        REDIS[("Redis<br/>search + read cache")]
        OBJ[("Object Storage (S3)<br/>attachments / blobs")]
    end

    WEB --> LB
    MOB --> LB
    LB --> AUTH
    LB --> DOCS
    LB --> SEARCHSVC
    LB --> COLLAB

    AUTH --> PG
    DOCS --> PG
    DOCS --> IDX
    DOCS --> OBJ
    IDX --> ES
    SEARCHSVC --> ES
    SEARCHSVC --> REDIS
    SEARCHSVC --> PG
    DOCS --> REDIS
    COLLAB --> PG
```

## Write path (create / update a document)

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Document Service
    participant PG as PostgreSQL
    participant IDX as Indexing Pipeline
    participant ES as Elasticsearch
    participant R as Redis

    C->>API: PUT /documents/{id} (+ JWT)
    API->>API: authorize (>= editor on doc)
    API->>PG: update row + append DocumentVersion
    API->>PG: append CollaborationLog
    PG-->>API: committed
    API->>IDX: sync(document)
    IDX->>ES: upsert into inverted index
    API->>R: invalidate doc + search caches
    API-->>C: 200 updated (new version)
```

## Read / search path

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Search Service
    participant R as Redis
    participant PG as PostgreSQL
    participant ES as Elasticsearch

    C->>S: GET /search?q=... (+ JWT)
    S->>R: lookup cached result (per-user key)
    alt cache hit
        R-->>S: cached hits
        S-->>C: results (cached=true)
    else cache miss
        S->>PG: resolve visible document ids (ACL)
        S->>ES: query, filtered by visible ids
        ES-->>S: ranked hits + highlights
        S->>R: store result (TTL)
        S-->>C: results (cached=false)
    end
```

## ASCII fallback (if Mermaid does not render)

```
         Web / Mobile clients
                  |
        Load Balancer / Gateway
                  |
   ----------------------------------------
   |        KnowledgeHub API (N pods)      |
   |  Auth | Documents | Search | Collab   |
   |          + Indexing Pipeline          |
   ----------------------------------------
       |          |          |        |
   PostgreSQL  Elasticsearch Redis  Object
   (source of  (full-text   (cache) Storage
    truth)      index)              (blobs)
```
