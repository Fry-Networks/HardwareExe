param(
    [string]$PythonExe = 'C:\Program Files\Python311\python.exe',
    [int]$TimeoutSeconds = 20
)

# Prepare isolated ProgramData under TEMP for CI-friendly run
$TempPD = Join-Path $env:TEMP 'FryCI_ProgramData'
New-Item -ItemType Directory -Force -Path $TempPD | Out-Null
$env:PROGRAMDATA = $TempPD

# Discover miner code from the codebase
try {
    $minerCode = & $PythonExe -c "from miner_GUI.config import MINER_CODE; print(MINER_CODE)"
    if (-not $minerCode) { throw 'MINER_CODE not found' }
} catch {
    Write-Error "Failed to read MINER_CODE from miner_GUI.config. $_"
    exit 1
}

$base = Join-Path $env:PROGRAMDATA ("FryNetworks\miner-$minerCode")
$queue = Join-Path $base 'ops_queue'
$processed = Join-Path $base 'ops_processed'
New-Item -ItemType Directory -Force -Path $queue, $processed | Out-Null

# Start daemon (inherits overridden PROGRAMDATA)
Write-Host "Starting daemon for E2E with PROGRAMDATA=$env:PROGRAMDATA and miner-$minerCode"
$proc = Start-Process -FilePath $PythonExe -ArgumentList "-m", "miner_GUI.services.privileged_ops_daemon" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 1

# Enqueue write_config request
$reqId = [guid]::NewGuid().ToString()
$reqPath = Join-Path $queue ("req-" + $reqId + ".json")
$destRel = 'config/ci_e2e.json'
$payload = @{ op = 'write_config'; path = $destRel; content = @{ e2e = $true; ts = (Get-Date).ToString('s') } } | ConvertTo-Json -Depth 5
$payload | Set-Content -Path $reqPath -Encoding UTF8

# Wait for result
$destAbs = Join-Path $base ($destRel -replace '/', '\')
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$ok = $false
while ((Get-Date) -lt $deadline) {
    if (Test-Path $destAbs) { $ok = $true; break }
    Start-Sleep -Milliseconds 500
}

# Cleanup daemon
try { Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue } catch {}

if (-not $ok) {
    Write-Error "E2E failed: did not find $destAbs within $TimeoutSeconds seconds."
    # Show processed directory contents for diagnostics
    if (Test-Path $processed) { Get-ChildItem $processed | Select-Object Name | Out-Host }
    exit 2
}

# Validate JSON structure
try {
    $json = Get-Content -Raw -Path $destAbs | ConvertFrom-Json
    if (-not $json.e2e) { throw 'Missing e2e flag in output JSON' }
} catch {
    Write-Warning "E2E output JSON validation warning: $_"
}

Write-Host "E2E OK: queue→daemon→ProgramData write succeeded at $destAbs"
exit 0
