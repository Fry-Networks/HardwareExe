# FryNetworks Installer - IPC Queue Setup README

This guide is for the installer team to configure the NSSM service and ACLs for the new filesystem IPC queue. The queue enables the GUI (user mode) to request privileged file writes without UAC prompts.

## Goals

- Allow GUI to enqueue write requests into ProgramData `ops_queue` without admin.
- Run service as LocalSystem to process requests and write ProgramData files.
- Keep all privileged operations inside the service.

## ProgramData Layout

```
%PROGRAMDATA%\FryNetworks\miner-{CODE}\
  ops_queue\            # Users: Modify (installer must set ACL)
  ops_processed\        # Service-owned; logs and processed markers
  config\               # Service-owned
  status\               # Service-owned
  measurements\         # Service-owned
```

## ACL Configuration

Set ACLs so that standard users can write ONLY to `ops_queue`.

```powershell
$base = "$env:ProgramData\FryNetworks\miner-BM"
$queue = Join-Path $base 'ops_queue'
$processed = Join-Path $base 'ops_processed'

# Ensure directories exist
New-Item -ItemType Directory -Force -Path $base, $queue, $processed | Out-Null

# Grant Users modify on ops_queue only
icacls $queue /grant:r "Users:(OI)(CI)(M)" /t

# Remove Users from base and processed (optional hardening)
icacls $base /remove:g Users /t
icacls $processed /remove:g Users /t

# Ensure SYSTEM and Administrators have Full control
icacls $base /grant:r "SYSTEM:(OI)(CI)(F)" "Administrators:(OI)(CI)(F)" /t
```

Notes:
- `(OI)(CI)` propagates permissions to files and subfolders.
- Use `/inheritance:d` if you want to disable inherited permissions and set explicit ACLs.

## NSSM Service Configuration

Run the daemon as the service app. Keep existing firewall AppPreStart.

```powershell
# Example NSSM setup
$n = 'FryMinerService'
$py = 'C:\Program Files\Python311\python.exe'  # or embedded python path

nssm stop $n
nssm set $n AppPath $py
nssm set $n AppParameters "-m miner_GUI.services.privileged_ops_daemon"

# Optional: keep firewall setup on pre-start
nssm set $n AppPreStart "python -m miner_GUI.services.privileged_ops --setup-mysterium-firewall"

# Restart service
nssm start $n
```

## Health & Monitoring

- The daemon writes processed results to `ops_processed/<id>.done.json`.
- Consider adding a watchdog: check for recent `.done.json` timestamps.
- Logs use `log_step`; ensure service log sinks capture these (file/eventlog).

## Testing Checklist

1. After installation, validate ACLs:
```powershell
$queue = "$env:ProgramData\FryNetworks\miner-BM\ops_queue"
# As a normal user, create a test file
"test" | Set-Content -Path (Join-Path $queue 'probe.txt') -Encoding UTF8
```
2. Ensure the service can process a write_config request created by GUI.
3. Verify resulting files under `config\`, `status\`, and `measurements\`.

### Fast Automation & Probe

Use the bundled scripts to automate setup and verify processing:

```powershell
# Run as Administrator (installs NSSM service, sets ACLs)
cd C:\Users\jimbo\Documents\GitHub\DevTesting\HardwareExe\scripts
./Install-IPC.ps1 -Code BM -ServiceName FryMinerService -PythonExe "C:\Program Files\Python311\python.exe" -SetupFirewall

# Run as a normal user (probes ACLs and enqueues a config write)
./Probe-QueueACL.ps1 -Code BM -TimeoutSeconds 15
```

## Troubleshooting

- GUI logs `ops_queue_mkdir_failed`: ACLs likely missing; ensure Users: Modify on ops_queue.
- Service logs `privileged_write_config_file_failed`: check file path and disk space.
- Base64 decode errors: ensure GUI provides valid encrypted bytes.
- Processed files piling up: daemon not running or lacking permissions.
 - `path not allowed` in processed markers: daemon enforces allowlists (only `config/*.json`, `status/*.json`).
 - `invalid group` in processed markers: measurement group must be alphanumeric with `-` or `_`.

## Security Considerations

- Only `ops_queue` is writable by Users; all other ProgramData folders remain service-owned.
- Queue files are JSON; service performs minimal validation—avoid executing arbitrary content.
- Consider adding filename/path allowlists in the daemon for stricter control (e.g., only `config/*.json`, `status/*.json`, `measurements/*.enc`).

## Rollback Plan

- Stop daemon service; revert GUI to direct privileged writes (UAC) if necessary.
- Remove Users ACL from `ops_queue` to disable enqueuing.

## Contact

- Service devs: see `docs/README_ServiceIPC.md` for processing details.
- GUI devs: use `miner_GUI.utils.ops_queue_client` to enqueue requests.
