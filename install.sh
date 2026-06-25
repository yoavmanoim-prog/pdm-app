#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# On-site installer. Run this on the factory server AFTER unpacking the release
# tarball. It loads the bundled images and starts the stack — no internet needed.
#
#   tar xzf pdm-onsite-<version>.tar.gz
#   cd pdm-onsite-<version>
#   ./install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Loading container images (docker load)…"
docker load -i images.tar

# First run: create .env from the template and stop so the operator can set
# secrets. Re-running install.sh after that proceeds to start the stack.
if [[ ! -f .env ]]; then
  cp .env.onsite.example .env
  # Pin the version that shipped in this bundle.
  if [[ -f .version ]]; then
    grep -v '^VERSION=' .env > .env.tmp && cat .version >> .env.tmp && mv .env.tmp .env
  fi
  echo ""
  echo "‼  Created .env from template. EDIT IT NOW and set strong values for:"
  echo "     DB_PASSWORD, JWT_SECRET, BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD"
  echo "   Tip: JWT_SECRET=\$(openssl rand -hex 32)"
  echo "   Then re-run ./install.sh to start."
  exit 0
fi

echo "==> Starting the stack…"
# No --build: we run the images we just loaded.
docker compose -f docker-compose.onsite.yml up -d

echo ""
echo "✓ MechDocs is starting."
echo "  Open:  http://<this-server-ip>/"
echo "  Log in with the BOOTSTRAP_ADMIN_EMAIL / PASSWORD from .env, then change the password."
