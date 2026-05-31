# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PDM App** (also referred to as MechDocs internally) is a FastAPI-based backend service containerized with Docker and deployed to Kubernetes via Helm. The image is hosted on AWS ECR (`302954730632.dkr.ecr.eu-north-1.amazonaws.com/pdm-backend`).

## Local Development

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run the app locally
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The app exposes two endpoints:
- `GET /` — status check, returns app name
- `GET /health` — health probe used by Kubernetes liveness/readiness checks

## Docker

```bash
# Build the image
docker build -t pdm-backend ./backend

# Run the container
docker run -p 8000:8000 pdm-backend
```

## Helm Deployment

```bash
# Lint the chart
helm lint helm/backend

# Dry-run to preview rendered manifests
helm template pdm-backend helm/backend

# Deploy / upgrade
helm upgrade --install pdm-backend helm/backend --values helm/backend/values.yaml

# Override the image tag at deploy time
helm upgrade --install pdm-backend helm/backend --set image.tag=v1.2.3
```

## Architecture

```
pdm-app/
├── backend/          # FastAPI application
│   ├── app/main.py   # All routes live here (single-file app for now)
│   ├── requirements.txt
│   └── Dockerfile    # python:3.12-slim, runs uvicorn on port 8000
└── helm/backend/     # Kubernetes Helm chart
    ├── Chart.yaml
    ├── values.yaml   # Image tag, replicas, resources, autoscaling, ingress host
    └── templates/
        ├── deployment.yaml   # HPA-ready, liveness+readiness on /health
        ├── service.yaml      # ClusterIP on port 8000
        └── ingress.yaml      # nginx ingress, allows 50m body size for PDF uploads
```

The Helm chart uses HPA (Horizontal Pod Autoscaler) configured in `values.yaml` — scaling between 2–8 replicas at 70% CPU. ECR image pull uses the `ecr-secret` imagePullSecret which must exist in the target namespace before deploying.

The ingress annotation `nginx.ingress.kubernetes.io/proxy-body-size: "50m"` indicates the app is intended to handle large file uploads (PDFs).
