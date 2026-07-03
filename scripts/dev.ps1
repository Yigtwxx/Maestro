<#
.SYNOPSIS
    Start the full Maestro dev stack on Windows: infra (Docker), backend
    (FastAPI/uvicorn) and frontend (Next.js).

.DESCRIPTION
    - Brings up PostgreSQL, MongoDB and Qdrant via docker-compose (skippable).
    - Creates/uses the backend virtualenv, installs deps, runs Alembic migrations
      and launches uvicorn in this terminal.
    - Installs frontend deps and launches `npm run dev` in this terminal.
    - Both services share the current terminal; press Ctrl+C to stop them.

.EXAMPLE
    ./scripts/dev.ps1
    ./scripts/dev.ps1 -SkipInfra
    ./scripts/dev.ps1 -BackendPort 8001 -FrontendPort 3001
#>
[CmdletBinding()]
param(
    [switch]$SkipInfra,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $RepoRoot 'backend'
$Frontend = Join-Path $RepoRoot 'frontend'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

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
        try { docker compose up -d } catch { Write-Warning "docker compose failed: $_" }
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
try { & $VenvPy -m alembic -c (Join-Path $Backend 'alembic.ini') upgrade head }
catch { Write-Warning "Alembic migration failed (is Postgres up?): $_" }

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

Clear-Port $FrontendPort
Write-Step "Launching frontend on http://localhost:$FrontendPort"
$FrontendProc = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList '/c', "npm run dev -- --port $FrontendPort" `
    -WorkingDirectory $Frontend -NoNewWindow -PassThru

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
