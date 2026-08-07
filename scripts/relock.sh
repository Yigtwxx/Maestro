#!/usr/bin/env bash
#
# Regenerate backend/requirements*.txt with the exact uv commands CI checks
# against, so the "Lock freshness check" gate in .github/workflows/ci.yml
# passes.
#
# Why this exists: Dependabot does not use uv. It rewrites the locks in its own
# style, which differs from `uv pip compile --universal` three ways:
#
#   1. Environment markers are dropped. uvloop loses its
#      `sys_platform != 'win32'` guard and pywin32/colorama/async-timeout/tomli
#      disappear entirely. This is the load-bearing one -- uvloop publishes no
#      Windows wheel, so an unguarded pin makes `pip install` fail on a Windows
#      checkout, and the repo is developed on Windows.
#   2. Extras are written into the pin (`sqlalchemy[asyncio]`,
#      `httpx[brotli,http2,socks]`, `coverage[toml]`, `fakeredis[lua]`,
#      `scrapling[fetchers]`, `sentry-sdk[fastapi]`). uv resolves extras but
#      emits the bare name, so these are pure drift against the gate.
#   3. The dev lock's `# via -c requirements.txt` annotations collapse away.
#
# The gate compares byte-for-byte, so every pip Dependabot PR needs the locks
# regenerated before it can merge.
#
# This is deliberately a local script rather than a CI job. A push made with
# GITHUB_TOKEN does not start new workflow runs, so a bot that fixed the branch
# would leave the PR permanently unchecked; and a Dependabot pull_request event
# gets a read-only token, so it could not push at all without escalating to
# pull_request_target. Running it from a real account keeps both problems away.
#
# Usage:
#   ./scripts/relock.sh                 # regenerate on the current branch
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(dirname "$SCRIPT_DIR")/backend"

if [ "$#" -gt 0 ]; then
  echo "unexpected argument: $1 (this script takes none)" >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it: pipx install uv  (or) pip install uv" >&2
  exit 1
fi

cd "$BACKEND"
echo "uv $(uv --version | awk '{print $2}') - regenerating locks in $BACKEND"

# Copied verbatim from CI. --custom-compile-command pins the header line
# independently of how the command was typed, so an identical resolution
# invoked with a different argument order does not rewrite it.
#
# uv echoes the whole compiled lock to stdout on top of writing -o, which buries
# the diff this script exists to show; stderr (resolution errors) is kept.
uv pip compile requirements.in -o requirements.txt \
  --universal --python-version 3.11 --generate-hashes \
  --custom-compile-command "uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 --generate-hashes" >/dev/null

uv pip compile requirements-dev.in -o requirements-dev.txt \
  --universal --python-version 3.11 --generate-hashes -c requirements.txt \
  --custom-compile-command "uv pip compile requirements-dev.in -o requirements-dev.txt --universal --python-version 3.11 --generate-hashes -c requirements.txt" >/dev/null

if git diff --quiet -- requirements.txt requirements-dev.txt; then
  echo "Locks already match the .in files. Nothing to do."
  exit 0
fi

git --no-pager diff --stat -- requirements.txt requirements-dev.txt

cat <<'EOF'

Regenerated. Review the diff, then commit on the PR branch:

  git add backend/requirements.txt backend/requirements-dev.txt
  git commit -m "chore(backend): regenerate locks with the documented uv commands"
  git push

If CI still reports drift after this, your uv is older than the one CI installs
(it runs a bare `pip install uv`, i.e. the latest release). Run `uv self update`
and regenerate again.
EOF
