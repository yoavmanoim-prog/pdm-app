# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Behaviour Rules
1. Before every step — explain what you are about to do and why, like a teacher
2. When explaining — teach the concept behind the process, not just the steps
3. Keep explanations simple — avoid jargon, use real-world analogies
4. If a request is ambiguous — ask for clarification before building anything
5. When writing a file — add comments near important lines explaining what they do
6. At the end of every step — test the work before committing
7. Git discipline — always work on feature branches, never commit directly to main or develop

## Project Overview

**PDM (MechDocs)** — a Git-like Product Data Management system for engineering schematics.
Engineers commit changes to drawings, push to a remote vault, merge branches, and publish formal revisions (Rev A, Rev B...).

## Architecture

```
pdm-app/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # FastAPI app entry point
│   │   ├── database.py       # lazy DB connection (reads env var only when needed)
│   │   ├── models/           # SQLAlchemy database table definitions
│   │   │   ├── base.py       # shared Base class all models inherit from
│   │   │   ├── repository.py # Repository — top-level container like a GitHub repo
│   │   │   ├── document.py   # Document — a single engineering drawing
│   │   │   ├── commit.py     # Commit + CommitFile — git-like snapshots
│   │   │   ├── bom.py        # BOMEntry — assembly to parts relationships
│   │   │   ├── revision.py   # Revision — formal Rev A, Rev B releases
│   │   │   └── audit.py      # AuditEvent — immutable log of every action
│   │   ├── schemas/          # Pydantic request/response shapes (what the API accepts/returns)
│   │   ├── services/         # Business logic (vault sync, SVG diff, engineering rules)
│   │   └── routers/          # API endpoint definitions
│   ├── alembic/              # database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 # React + Vite UI
├── helm/backend/             # Kubernetes Helm chart
├── docker-compose.yml        # local dev — runs local-vault + remote-vault + 2 postgres DBs
└── grafana/                  # Grafana dashboard JSON files
```

## Key Concepts

- **Two-vault system** — local vault (engineer's workspace, port 8000) + remote vault (shared server, port 8001)
- **Commits** — every change creates a commit with a hash, author, message, and SVG diff
- **Branches** — engineers work in isolation, merges propagate drawing changes
- **Revisions** — formal releases (Rev A, B, C...) with no skipping allowed
- **BOM** — Bill of Materials links assembly drawings to their component parts
- **Audit log** — every action is recorded and can never be deleted

## Local Development

```bash
# Start both vaults + databases
docker compose up

# Local vault: http://localhost:8000
# Remote vault: http://localhost:8001
```

## Git Flow

```
feature/* → pdm-dev      (auto-deploy on push)
develop   → pdm-staging  (auto-deploy on push)
v* tag    → pdm-production (auto-deploy on tag)
```

## Infrastructure

- **EKS** — 4 t3.small nodes, us-east-1
- **RDS** — managed PostgreSQL (pdm-prod-eks-postgres.ci3ceikmuv20.us-east-1.rds.amazonaws.com)
- **S3** — PDF/SVG storage (pdm-docs-production)
- **ECR** — Docker image registry (302954730632.dkr.ecr.us-east-1.amazonaws.com)
- **ArgoCD** — GitOps deployments from pdm-gitops repo
