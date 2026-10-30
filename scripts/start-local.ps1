# Start the local milestone services. Run from any directory in PowerShell.
param([int]$ApiPort = 0)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$logDir = Join-Path $projectRoot 'tmp'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$vite = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$workerPidFile = Join-Path $logDir 'worker.pid'
$frontendEnv = Join-Path $frontendDir '.env.local'
$frontendEnvLines = @()
if (Test-Path -LiteralPath $frontendEnv) { $frontendEnvLines = @(Get-Content -LiteralPath $frontendEnv) }
if ($ApiPort -eq 0) {
    $savedTarget = $frontendEnvLines | Where-Object { $_ -match '^VITE_API_PROXY_TARGET=http://127\.0\.0\.1:(\d+)$' } | Select-Object -First 1
    if ($savedTarget -and $savedTarget -match ':(\d+)$') { $ApiPort = [int]$Matches[1] } else { $ApiPort = 8000 }
}
if ($ApiPort -lt 1024 -or $ApiPort -gt 65535) { throw 'Choose an API port between 1024 and 65535.' }
$frontendEnvLines = @($frontendEnvLines | Where-Object { $_ -notmatch '^VITE_API_PROXY_TARGET=' })
$frontendEnvLines += "VITE_API_PROXY_TARGET=http://127.0.0.1:$ApiPort"
Set-Content -LiteralPath $frontendEnv -Value $frontendEnvLines -Encoding UTF8
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment missing. Follow the setup steps in README.md first.' }
if (-not (Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies missing. Run pnpm install in frontend first.' }
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCommand) { $node = $nodeCommand.Source } else {
    $node = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (-not (Test-Path -LiteralPath $node)) { throw 'Node.js was not found. Install Node.js and retry.' }
}

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Test-Api {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 2
        return $health.service -eq 'document-intake' -and $health.status -eq 'ok'
    } catch { return $false }
}
function Start-LoggedProcess([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory, [string]$Name) {
    return Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "$Name.out.log") -RedirectStandardError (Join-Path $logDir "$Name.err.log")
}

if (Test-Api) {
    Write-Host "API is already responding on port $ApiPort."
} elseif (Test-Port $ApiPort) {
    throw "Port $ApiPort is occupied by another service. Choose a different -ApiPort."
} else {
    $env:FRONTEND_ORIGIN = 'http://127.0.0.1:5174'
    $apiProcess = Start-LoggedProcess $python @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") $backendDir 'api'
    Write-Host "Started API (PID $($apiProcess.Id))."
}

$workerRunning = $false
if (Test-Path -LiteralPath $workerPidFile) {
    $savedPid = (Get-Content -LiteralPath $workerPidFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -match 'app\.worker' -and $process.ExecutablePath -eq $python) { $workerRunning = $true }
    }
}
# Also recognize a worker started manually from this project's virtual environment.
if (-not $workerRunning) {
    $existingWorker = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'app\.worker' -and $_.ExecutablePath -eq $python } | Select-Object -First 1
    if ($existingWorker) { $workerRunning = $true; $savedPid = $existingWorker.ProcessId }
}
if ($workerRunning) { Write-Host "Worker is already running (PID $savedPid)." } else {
    $worker = Start-LoggedProcess $python @('-m', 'app.worker') $backendDir 'worker'
    Set-Content -LiteralPath $workerPidFile -Value $worker.Id
    Write-Host "Started worker (PID $($worker.Id))."
}

if (Test-Port 5174) {
    Write-Warning 'Port 5174 is already in use. The existing listener was left untouched; verify it is this project before opening it.'
} else {
    # Quote the Vite path because the workspace path can contain spaces.
    $frontend = Start-LoggedProcess $node @("`"$vite`"", '--host', '127.0.0.1', '--port', '5174', '--strictPort') $frontendDir 'frontend'
    Write-Host "Started frontend (PID $($frontend.Id))."
}
Write-Host 'Open http://127.0.0.1:5174 after the services have started. Logs are in tmp/.'
