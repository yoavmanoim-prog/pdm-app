#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build a PRODUCTION on-site release: versioned images packed into one offline
# tarball you can carry to an air-gapped factory server (no registry/internet).
#
# The version is the latest v* tag on the MAIN branch — never a hand-set/dev
# value. Releases only happen on tagged production commits (the same v* tags that
# drive the cloud deploy), so the on-site image tag always matches main's tag.
#
#   ./release.sh                # version = latest v* tag on main
#   ./release.sh 2.0.1          # or pass it explicitly (must match x.y.z)
#
# Versioning (semantic, production only):
#   bug fix  → patch  x.y.(z+1)   2.0.0 → 2.0.1
#   feature  → minor  x.(y+1).0   2.0.1 → 2.1.0
#
# Output:  pdm-onsite-<version>.tar.gz  containing:
#   images.tar                  (docker save of backend + frontend + postgres)
#   docker-compose.onsite.yml
#   .env.onsite.example
#   install.sh
#   README.onsite.md
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

# Version source of truth: the latest v* tag on the MAIN branch (production
# releases live on main). You don't have to be sitting on the tagged commit —
# we read the most recent version tag reachable from main. Strip the leading
# "v" → image tag. An explicit arg overrides it (CI passes the pushed tag).
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  # prefer the local main ref; fall back to origin/main (detached/CI checkouts).
  RAW_TAG="$(git describe --tags --abbrev=0 --match 'v*' main 2>/dev/null \
             || git describe --tags --abbrev=0 --match 'v*' origin/main 2>/dev/null \
             || true)"
  if [[ -z "$RAW_TAG" ]]; then
    echo "error: no v* tag found on main. Tag the production release first, e.g.:" >&2
    echo "       git tag v2.0.1 && git push origin v2.0.1" >&2
    exit 1
  fi
  VERSION="${RAW_TAG#v}"     # v2.0.1 → 2.0.1
fi

# Enforce a strict x.y.z semantic version — no "latest", no "dev" in releases.
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: version '$VERSION' is not semantic x.y.z (e.g. 2.0.1)" >&2
  exit 1
fi

PG_IMAGE="postgres:16-alpine"
BACKEND_IMAGE="pdm-backend:${VERSION}"
FRONTEND_IMAGE="pdm-frontend:${VERSION}"
OUT_DIR="dist/pdm-onsite-${VERSION}"
TARBALL="pdm-onsite-${VERSION}.tar.gz"

echo "==> Building backend image  ${BACKEND_IMAGE}"
docker build -t "${BACKEND_IMAGE}" ./backend

echo "==> Building frontend image ${FRONTEND_IMAGE}"
docker build -t "${FRONTEND_IMAGE}" ./frontend

echo "==> Pulling ${PG_IMAGE}"
docker pull "${PG_IMAGE}"

echo "==> Staging release in ${OUT_DIR}"
rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

# Save all three images into one archive the site loads with `docker load`.
echo "==> Saving images → images.tar"
docker save -o "${OUT_DIR}/images.tar" \
  "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}" "${PG_IMAGE}"

# Ship the compose file, the env template, the installer and the docs.
cp docker-compose.onsite.yml "${OUT_DIR}/"
cp .env.onsite.example       "${OUT_DIR}/"
cp install.sh                "${OUT_DIR}/"
cp README.onsite.md          "${OUT_DIR}/" 2>/dev/null || true

# Pin the bundle's default VERSION to this release so `up` runs these exact images.
echo "VERSION=${VERSION}" > "${OUT_DIR}/.version"

echo "==> Packing ${TARBALL}"
tar -C dist -czf "${TARBALL}" "pdm-onsite-${VERSION}"

echo ""
echo "✓ Release ready: ${TARBALL}"
echo "  Copy it to the on-site server, then: tar xzf ${TARBALL} && cd pdm-onsite-${VERSION} && ./install.sh"
