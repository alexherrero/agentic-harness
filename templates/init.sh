#!/usr/bin/env bash
# init.sh — one-shot script to boot the dev environment for this project.
# Edit the commands below to match how this project actually runs.
#
# Every /work and /review session should be able to run this to get to
# a known-good starting state without burning context figuring it out.

set -euo pipefail

echo "==> install deps"
# npm install      # or yarn, pnpm, go mod download, pip install, etc.

echo "==> start dev server (background)"
# npm run dev &
# echo $! > .harness/.dev-server.pid

echo "==> ready"
