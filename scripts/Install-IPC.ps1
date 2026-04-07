param(
    [Parameter(Mandatory = $true)][ValidateSet('BM','IRM','ISM','AEM','ODM','OSM','RDN','SDN','SVN','IDM','IRM')][string]$Code,
    [string]$ServiceName = 'FryMinerService',
    [string]$PythonExe = 'C:\Program Files\Python311\python.exe',
    [switch]$SetupFirewall
)

# Require Administrator
$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Error 'This script must be run as Administrator.'
    exit 1
}

$base = Join-Path $env:ProgramData ("FryNetworks\miner-$Code")
$queue = Join-Path $base 'ops_queue'
$processed = Join-Path $base 'ops_processed'
$config = Join-Path $base 'config'
$status = Join-Path $base 'status'
$measurements = Join-Path $base 'measurements'

Write-Host "Creating ProgramData directories under $base"
New-Item -ItemType Directory -Force -Path $base, $queue, $processed, $config, $status, $measurements | Out-Null

Write-Host 'Setting ACLs: Users Modify on ops_queue; SYSTEM/Administrators Full elsewhere'
# Grant Users modify ONLY on ops_queue
icacls $queue /grant:r "Users:(OI)(CI)(M)" /t | Out-Null
# Ensure SYSTEM and Administrators have Full control recursively
icacls $base /grant:r "SYSTEM:(OI)(CI)(F)" "Administrators:(OI)(CI)(F)" /t | Out-Null
# Remove Users from base and processed (best-effort)
icacls $base /remove:g Users /t 2>$null | Out-Null
icacls $processed /remove:g Users /t 2>$null | Out-Null

# NSSM service configuration
$ns = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $ns) {
    Write-Warning 'NSSM is not found on PATH. Install NSSM and rerun to configure the service.'
} else {
    Write-Host "Configuring NSSM service '$ServiceName'"
    try {
        & nssm stop $ServiceName 2>$null | Out-Null
    } catch {}
    # Install or update service definition
    & nssm install $ServiceName $PythonExe "-m" "miner_GUI.services.privileged_ops_daemon" | Out-Null

    if ($SetupFirewall.IsPresent) {
        & nssm set $ServiceName AppPreStart "$PythonExe -m miner_GUI.services.privileged_ops --setup-mysterium-firewall" | Out-Null
    }

    # Start service
    & nssm start $ServiceName | Out-Null
    Write-Host "Service '$ServiceName' started."
}

Write-Host 'Done. Verify Users can write to ops_queue and the service processes requests.'
