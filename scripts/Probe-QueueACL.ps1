param(
    [Parameter(Mandatory = $true)][ValidateSet('BM','IRM','ISM','AEM','ODM','OSM','RDN','SDN','SVN','IDM','IRM')][string]$Code,
    [int]$TimeoutSeconds = 15
)

$base = Join-Path $env:ProgramData ("FryNetworks\miner-$Code")
$queue = Join-Path $base 'ops_queue'

Write-Host "Queue path: $queue"
if (-not (Test-Path $queue)) {
    Write-Error "Queue folder not found. Run Install-IPC.ps1 as Administrator first."
    exit 1
}

# ACL probe: attempt to write as current user
$probeFile = Join-Path $queue ("probe-" + [guid]::NewGuid().ToString() + ".txt")
try {
    'acl-probe' | Set-Content -Path $probeFile -Encoding UTF8 -ErrorAction Stop
    Write-Host "ACL probe: success writing $probeFile"
} catch {
    Write-Error "ACL probe: failed to write to ops_queue. Ensure Users have Modify permissions."
    exit 1
}

# Service processing probe: enqueue a write_config request
$reqId = [guid]::NewGuid().ToString()
$reqFile = Join-Path $queue ("req-" + $reqId + ".json")
$destRel = 'config/installer_probe.json'
$payload = @{ op = 'write_config'; path = $destRel; content = @{ probe = $true; timestamp = (Get-Date).ToString('s') } } | ConvertTo-Json -Depth 5

try {
    $payload | Set-Content -Path $reqFile -Encoding UTF8 -ErrorAction Stop
    Write-Host "Enqueued request: $reqFile"
} catch {
    Write-Error "Failed to enqueue JSON request."
    exit 1
}

# Wait for service to process
$destAbs = Join-Path $base ($destRel -replace '/', '\')
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $destAbs) {
        Write-Host "Service processing OK: found $destAbs"
        exit 0
    }
    Start-Sleep -Seconds 1
}

Write-Warning "Timeout: did not find $destAbs. Ensure service is running and has permissions."
exit 2
