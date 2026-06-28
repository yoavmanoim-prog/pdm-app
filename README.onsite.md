# MechDocs — On-Site (AWS-free) Deployment

A self-contained build of MechDocs that runs on **one Linux server** with **no
AWS**. Files are stored on a local disk volume instead of S3; everything else
(backend, frontend, PostgreSQL) runs in containers via Docker Compose.

This is a **separate app** from the cloud (EKS) deployment and shares the same
source. The only difference is the entrypoint: it runs `app.onsite:app`, which
swaps S3 storage for the local filesystem. The cloud build is untouched.

---

## What's different from the cloud build

| Concern   | Cloud (EKS)            | On-site                                  |
|-----------|------------------------|------------------------------------------|
| Storage   | Amazon S3              | Local disk volume (`vault-data`)         |
| File links| S3 presigned URLs      | HMAC-signed, expiring `/api/files/...`    |
| Entrypoint| `app.main:app`         | `app.onsite:app`                          |
| Secrets   | AWS Secrets Manager    | `.env` file on the server                 |
| Database  | RDS                    | bundled `postgres:16-alpine` container    |

---

## Build a release

The version always comes from the **production git tag** (`v*`) — never a
hand-set/dev value. Bumped **only** when cutting a production release:

- bug fix → patch: `2.0.0 → 2.0.1`
- feature → minor: `2.0.1 → 2.1.0`

**Automatic (recommended):** pushing a `v*` tag triggers the
[On-site Release workflow](.github/workflows/onsite-release.yml), which builds
the bundle and attaches `pdm-onsite-<version>.tar.gz` to the GitHub release.

```bash
git tag v2.0.1 && git push origin v2.0.1
# → download pdm-onsite-2.0.1.tar.gz from the release page
```

**Manual** (on a machine with Docker), from a tagged commit:

```bash
cd pdm-app
git tag v2.0.1        # if not already tagged
./release.sh          # version read from the tag → pdm-onsite-2.0.1.tar.gz
```

The tarball contains the images (`docker save`), the compose file, the `.env`
template, `install.sh`, and this README.

---

## Install at the site (air-gapped is fine)

Requires Docker (Docker Desktop on Windows, in Linux-container mode — the default).

**Linux / macOS:**
```bash
tar xzf pdm-onsite-2.0.1.tar.gz
cd pdm-onsite-2.0.1
./install.sh                # loads images, creates .env from template
# edit .env: set DB_PASSWORD, JWT_SECRET, BOOTSTRAP_ADMIN_* (see hints inside)
./install.sh                # run again to start the stack
```

**Windows (PowerShell):**
```powershell
tar xzf pdm-onsite-2.0.1.tar.gz   # tar ships with Windows 10/11
cd pdm-onsite-2.0.1
# if scripts are blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1                # loads images, creates .env from template
# edit .env (Notepad): DB_PASSWORD, JWT_SECRET, BOOTSTRAP_ADMIN_*
.\install.ps1                # run again to start the stack
```

The app itself is OS-agnostic (Linux containers run on Docker Desktop for Windows); only the installer differs per OS.

Then open `http://<server-ip>/` and log in with the bootstrap admin from `.env`
(change the password immediately).

---

## Local test (build + run on your machine)

```bash
cd pdm-app
cp .env.onsite.example .env      # then edit secrets
docker compose -f docker-compose.onsite.yml up -d --build
open http://localhost/
```

---

## Where the data lives & backups

Two Docker named volumes hold all state:

- `vault-data` — the PDF/SVG files (S3 replacement)
- `db-data` — the PostgreSQL database

Back both up together (stop the stack or snapshot). Example:

```bash
docker run --rm -v pdm-onsite_vault-data:/v -v "$PWD:/out" alpine \
  tar czf /out/vault-data.tgz -C /v .
docker run --rm -v pdm-onsite_db-data:/v -v "$PWD:/out" alpine \
  tar czf /out/db-data.tgz -C /v .
```

---

## Notes

- HTTPS/TLS is not included — put a reverse proxy (or the factory's existing
  one) in front if you need it.
- `JWT_SECRET` signs both login tokens **and** file-download links. Keep it
  secret and stable; rotating it logs everyone out and invalidates open file links.
