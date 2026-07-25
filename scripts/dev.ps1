<#
.SYNOPSIS
    Start the full Maestro dev stack on Windows: infra (Docker), backend
    (FastAPI/uvicorn) and frontend (Next.js).

.DESCRIPTION
    - Brings up PostgreSQL, MongoDB and Qdrant via docker-compose (skippable).
    - Creates/uses the backend virtualenv, installs deps, runs Alembic migrations,
      seeds the featured marketplace teams and launches uvicorn in this terminal.
    - Installs frontend deps and launches `npm run dev` in this terminal.
    - Both services share the current terminal; press Ctrl+C to stop them.

.EXAMPLE
    ./scripts/dev.ps1
    ./scripts/dev.ps1 -SkipInfra
    ./scripts/dev.ps1 -SkipSeed
    ./scripts/dev.ps1 -BackendPort 8001 -FrontendPort 3001
#>
[CmdletBinding()]
param(
    [switch]$SkipInfra,
    [switch]$SkipSeed,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $RepoRoot 'backend'
$Frontend = Join-Path $RepoRoot 'frontend'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# Blocks until every compose service with a healthcheck reports healthy. Without
# this the script raced straight into pip/alembic while the four containers were
# still warming up, so the Docker memory spike and the Next.js compile — the two
# heaviest phases — landed in the same window and exhausted host RAM.
function Wait-Infra([int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        # `docker compose ps` emits one JSON object per line (not a JSON array).
        $lines = @(docker compose ps --format json 2>$null) | Where-Object { $_ }
        if ($lines) {
            $states = $lines | ForEach-Object {
                try { $_ | ConvertFrom-Json } catch { $null }
            } | Where-Object { $_ }
            # Qdrant declares no healthcheck; an empty Health means "running is enough".
            $pending = $states | Where-Object { $_.Health -and $_.Health -ne 'healthy' }
            if ($states.Count -gt 0 -and -not $pending) { return }
        }
        Start-Sleep -Seconds 2
    }
    Write-Warning "Infra did not report healthy within ${TimeoutSeconds}s; continuing anyway."
}

# Turbopack's persistent dev cache is disabled in next.config.ts, so .next should
# stay small. This is a backstop: a stale multi-GB .next gets memory-mapped on
# dev-server start and is exactly what produced `os error 1450` before.
function Clear-StaleNextCache([string]$Path, [int]$ThresholdMB = 600) {
    if (-not (Test-Path $Path)) { return }
    $bytes = (Get-ChildItem $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    $sizeMB = [int]($bytes / 1MB)
    if ($sizeMB -lt $ThresholdMB) { return }
    Write-Warning "frontend/.next is ${sizeMB}MB (threshold ${ThresholdMB}MB); removing it to avoid an out-of-memory dev start."
    Remove-Item $Path -Recurse -Force -ErrorAction SilentlyContinue
}

function Clear-Port([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Warning "Port $Port is in use by '$($proc.ProcessName)' (PID $procId); killing it."
            # /T kills the whole tree: dev servers spawn child processes
            taskkill /PID $procId /T /F | Out-Null
        }
    }
    Start-Sleep -Milliseconds 500
}

# --- 1. Infra (Docker) ----------------------------------------------------
if (-not $SkipInfra) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Step 'Starting infra (Postgres, MongoDB, Qdrant) via docker-compose'
        Push-Location $RepoRoot
        try {
            docker compose up -d
            Write-Host 'Waiting for infra to become healthy...'
            Wait-Infra
        }
        catch { Write-Warning "docker compose failed: $_" }
        Pop-Location
    }
    else {
        Write-Warning 'Docker not found; skipping infra. Use -SkipInfra to silence this.'
    }
}

# --- 2. Backend -----------------------------------------------------------
Write-Step 'Preparing backend'
$Venv = Join-Path $Backend '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'

if (-not (Test-Path $VenvPy)) {
    Write-Host 'Creating virtualenv...'
    $py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
    & $py -3 -m venv $Venv
}

if (-not (Test-Path (Join-Path $Backend '.env'))) {
    Copy-Item (Join-Path $RepoRoot '.env.example') (Join-Path $Backend '.env')
    Write-Warning 'Created backend/.env from .env.example — set real secrets before production.'
}

Write-Host 'Installing backend dependencies...'
& $VenvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Backend 'requirements.txt')

Write-Host 'Running database migrations (alembic upgrade head)...'
# Must run with the backend as CWD: alembic.ini resolves both `script_location`
# and `prepend_sys_path` relative to the working directory, not to the ini file.
# Passing -c alone is not enough — invoking this script from scripts/ made
# alembic look for ./alembic and fail with "Path doesn't exist: alembic".
Push-Location $Backend
try { & $VenvPy -m alembic -c 'alembic.ini' upgrade head }
catch { Write-Warning "Alembic migration failed (is Postgres up?): $_" }
finally { Pop-Location }

if (-not $SkipSeed) {
    Write-Host 'Seeding featured marketplace teams (idempotent)...'
    Push-Location $Backend
    # Seeding is cosmetic: a missing Mongo must not stop the dev stack coming up.
    try { & $VenvPy -m app.scripts.seed_marketplace }
    catch { Write-Warning "Marketplace seed failed (is MongoDB up?): $_" }
    finally { Pop-Location }
}

Clear-Port $BackendPort
Write-Step "Launching backend on http://localhost:$BackendPort"
$BackendProc = Start-Process -FilePath $VenvPy `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--port', "$BackendPort" `
    -WorkingDirectory $Backend -NoNewWindow -PassThru

# --- 3. Frontend ----------------------------------------------------------
Write-Step 'Preparing frontend'
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Write-Host 'Installing frontend dependencies...'
    Push-Location $Frontend
    cmd.exe /c 'npm install'
    Pop-Location
}

if (-not (Test-Path (Join-Path $Frontend '.env.local'))) {
    Copy-Item (Join-Path $Frontend '.env.local.example') (Join-Path $Frontend '.env.local')
}

Clear-StaleNextCache (Join-Path $Frontend '.next')

Clear-Port $FrontendPort
Write-Step "Launching frontend on http://localhost:$FrontendPort"
# Bound the V8 heap so a runaway dev server dies with a heap error instead of
# dragging the whole host into swap. This covers the JS side only — Turbopack's
# native memory-mapped cache is outside V8, which is why the real fix is
# `turbopackFileSystemCacheForDev: false` in next.config.ts.
$PrevNodeOptions = $env:NODE_OPTIONS
$env:NODE_OPTIONS = '--max-old-space-size=4096'
$FrontendProc = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList '/c', "npm run dev -- --port $FrontendPort" `
    -WorkingDirectory $Frontend -NoNewWindow -PassThru
# The child has inherited it; don't leave it set in the caller's session.
$env:NODE_OPTIONS = $PrevNodeOptions

Write-Host "`nMaestro is starting:" -ForegroundColor Green
Write-Host "  Backend : http://localhost:$BackendPort  (docs: /docs)"
Write-Host "  Frontend: http://localhost:$FrontendPort"
Write-Host 'Both services run in this terminal; press Ctrl+C to stop them.'

# --- 4. Wait & cleanup ------------------------------------------------------
try {
    Wait-Process -Id $BackendProc.Id, $FrontendProc.Id -ErrorAction SilentlyContinue
}
finally {
    # Kill whole process trees: uvicorn --reload and npm spawn child processes
    foreach ($proc in @($BackendProc, $FrontendProc)) {
        if ($proc -and -not $proc.HasExited) {
            taskkill /PID $proc.Id /T /F | Out-Null
        }
    }
}
