param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Database','Node','AI','Frontend','Test')]
    [string]$Component,
    [string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin',
    [string]$Tesseract = "$env:LOCALAPPDATA\AtopsyTools\Tesseract\tesseract.exe"
)
$ErrorActionPreference = 'Stop'
$backendPath = Split-Path $PSScriptRoot -Parent
$workspacePath = Split-Path $backendPath -Parent
$localPath = Join-Path $workspacePath '.local-test'
# This launcher deliberately addresses only the isolated synthetic database.
# It never edits .env, creates/drops tables, or migrates an existing user database.
$env:DATABASE_URL = 'postgresql://atopsy_test@127.0.0.1:15432/atopsy_synthetic'
$env:JWT_ACCESS_SECRET = 'synthetic-test-only-access-secret-32-characters'
$env:JWT_REFRESH_SECRET = 'synthetic-test-only-refresh-secret-32-characters'
$env:CORS_ORIGIN = 'http://localhost:3000'
$env:FASTAPI_URL = 'http://127.0.0.1:8001'
$env:RATE_LIMIT_MAX_REQUESTS = '5000'
$env:TESSERACT_CMD = $Tesseract
$env:STORAGE_ROOT = Join-Path $localPath 'evidence'
$env:TEMP_DIR = Join-Path $localPath 'temp'
Push-Location
try {
switch ($Component) {
    'Database' {
        $clusterPath = Join-Path $localPath 'pgdata'
        if (!(Test-Path -LiteralPath (Join-Path $clusterPath 'PG_VERSION'))) {
            throw 'Synthetic cluster is absent. Follow LOCAL_RUNBOOK.md to initialize a new isolated database.'
        }
        & (Join-Path $PostgresBin 'pg_ctl.exe') -D $clusterPath status
        if ($LASTEXITCODE -ne 0) { & (Join-Path $PostgresBin 'pg_ctl.exe') -D $clusterPath -l (Join-Path $localPath 'postgres.log') -o '-p 15432 -h 127.0.0.1' start }
    }
    'Node' {
        Set-Location (Join-Path $backendPath 'server')
        & node dist/server.js
    }
    'AI' {
        Set-Location (Join-Path $backendPath 'ai')
        & ./venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
    }
    'Frontend' {
        Set-Location (Join-Path $workspacePath 'frontend')
        & node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 3000
    }
    'Test' {
        if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) {
            throw 'Stop the AI service before failure-injection tests; keep the Node service and database running.'
        }
        Set-Location (Join-Path $backendPath 'ai')
        $env:TEST_DATABASE_URL = $env:DATABASE_URL
        $env:PYTHONPATH = '.'
        & ./venv/Scripts/python.exe tests/test_integrated_workflow.py
    }
}
if ($LASTEXITCODE -ne 0) { throw "$Component exited with code $LASTEXITCODE" }
} finally { Pop-Location }
