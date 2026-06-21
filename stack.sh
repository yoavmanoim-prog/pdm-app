#!/usr/bin/env bash
# Switch between the two MechDocs vault stacks. They share host ports
# (8000/5173/5432), so only one can run at a time — this brings the other down
# first, then the one you asked for.
#
#   ./stack.sh dev      fully-local dev env         (docker-compose.yml)
#   ./stack.sh stage    dev against AWS staging     (docker-compose.staging.yml)
#   ./stack.sh down     stop both stacks
#   ./stack.sh status   show what's running
#   ./stack.sh logs     follow logs of the running stack
#
# Extra args pass through to `up`, e.g. after a requirements change:
#   ./stack.sh stage --build
set -euo pipefail
cd "$(dirname "$0")"

DEV=(docker compose)                                   # project: pdm-app
STAGE=(docker compose -f docker-compose.staging.yml)   # project: pdm-stage

case "${1:-}" in
  dev)
    "${STAGE[@]}" down
    "${DEV[@]}" up -d "${@:2}"
    echo "✓ dev stack up  → http://localhost:5173  (local remote-vault)"
    echo "  logs: ./stack.sh logs"
    ;;
  stage|staging)
    "${DEV[@]}" down
    "${STAGE[@]}" up -d "${@:2}"
    echo "✓ staging stack up  → http://localhost:5173  (auth/sync → AWS staging)"
    echo "  sign in with your STAGING account; logs: ./stack.sh logs"
    ;;
  down)
    "${DEV[@]}" down
    "${STAGE[@]}" down
    echo "✓ all stacks down (named DB volumes preserved)"
    ;;
  status)
    echo "── dev (pdm-app) ──";    "${DEV[@]}" ps
    echo "── stage (pdm-stage) ──"; "${STAGE[@]}" ps
    ;;
  logs)
    # follow whichever stack currently has a running local-vault
    if [ -n "$("${STAGE[@]}" ps -q local-vault 2>/dev/null)" ]; then
      "${STAGE[@]}" logs -f
    else
      "${DEV[@]}" logs -f
    fi
    ;;
  *)
    echo "usage: $0 {dev|stage|down|status|logs} [extra args for 'up']" >&2
    exit 1
    ;;
esac
