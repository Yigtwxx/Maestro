<#
.SYNOPSIS
    Regenerate backend/requirements*.txt with the exact uv commands CI checks
    against, so the "Lock freshness check" gate in .github/workflows/ci.yml
    passes.

.DESCRIPTION
    Dependabot does not use uv. It rewrites the locks in its own style, which
    differs from `uv pip compile --universal` three ways:

      1. Environment markers are dropped. uvloop loses its
         `sys_platform != 'win32'` guard and pywin32/colorama/async-timeout/
         tomli disappear entirely. This is the load-bearing one -- uvloop
         publishes no Windows wheel, so an unguarded pin makes `pip install`
         fail on a Windows checkout, and the repo is developed on Windows.
      2. Extras are written into the pin (`sqlalchemy[asyncio]`,
         `httpx[brotli,http2,socks]`, `coverage[toml]`, `fakeredis[lua]`,
         `scrapling[fetchers]`, `sentry-sdk[fastapi]`). uv resolves extras but
         emits the bare name, so these are pure drift against the gate.
      3. The dev lock's `# via -c requirements.txt` annotations collapse away.

    The gate compares byte-for-byte, so every pip Dependabot PR needs the locks
    regenerated before it can merge.

    This is deliberately a local script rather than a CI job. A push made with
    GITHUB_TOKEN does not start new workflow runs, so a bot that fixed the
    branch would leave the PR permanently unchecked; and a Dependabot
    pull_request event gets a read-only token, so it could not push at all
    without escalating to pull_request_target. Running it from a real account
    keeps both problems away.

.EXAMPLE
    ./scripts/relock.ps1
#>
[CmdletBinding()]
param()

# Deliberately NOT 'Stop'. Both native commands here write to stderr on the
# happy path -- uv reports "Resolved N packages" and git emits CRLF warnings --
# and Windows PowerShell turns any native stderr into a NativeCommandError when
# this is 'Stop', which would abort a perfectly successful run. Correctness
# comes from the explicit $LASTEXITCODE checks below instead, and leaving
# stderr on the console is what makes a real resolution error visible.
$ErrorActionPreference = 'Continue'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot 'backend'

if ($null -eq (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv not found. Install it: pipx install uv  (or) pip install uv'
}

Push-Location $backend
try {
    Write-Host "$(uv --version) - regenerating locks in $backend"

    # Copied verbatim from CI. --custom-compile-command pins the header line
    # independently of how the command was typed, so an identical resolution
    # invoked with a different argument order does not rewrite it.
    #
    # uv echoes the whole compiled lock to stdout on top of writing -o, which
    # buries the diff this script exists to show; stderr is left alone so a
    # resolution error still surfaces.
    uv pip compile requirements.in -o requirements.txt `
        --universal --python-version 3.11 --generate-hashes `
        --custom-compile-command "uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 --generate-hashes" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "uv pip compile failed for requirements.in (exit $LASTEXITCODE)" }

    uv pip compile requirements-dev.in -o requirements-dev.txt `
        --universal --python-version 3.11 --generate-hashes -c requirements.txt `
        --custom-compile-command "uv pip compile requirements-dev.in -o requirements-dev.txt --universal --python-version 3.11 --generate-hashes -c requirements.txt" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "uv pip compile failed for requirements-dev.in (exit $LASTEXITCODE)" }

    git diff --quiet -- requirements.txt requirements-dev.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Locks already match the .in files. Nothing to do.'
        return
    }

    git --no-pager diff --stat -- requirements.txt requirements-dev.txt

    Write-Host @'

Regenerated. Review the diff, then commit on the PR branch:

  git add backend/requirements.txt backend/requirements-dev.txt
  git commit -m "chore(backend): regenerate locks with the documented uv commands"
  git push

If CI still reports drift after this, your uv is older than the one CI installs
(it runs a bare `pip install uv`, i.e. the latest release). Run `uv self update`
and regenerate again.
'@
}
finally {
    Pop-Location
}
