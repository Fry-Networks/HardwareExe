# FryNetworks Miner GUI

Windows and Linux miner management GUI supporting BM, ISM, OSM, IDM, ODM, AEM, SVN, SDN, and RDN.

## Building

```powershell
# Windows (PowerShell)
powershell -NoProfile -ExecutionPolicy Bypass -File .\builders\build_all_windows.ps1 -Code <CODE> -Version <VERSION>
```

```bash
# Linux
./LINUX/build_linux.sh
```

**CODE** = `BM`, `ISM`, `OSM`, `IDM`, `ODM`, `AEM`, `SVN`, `SDN`, `RDN`
**VERSION** = `x.x.x` (e.g. `6.5.8`)

## Releasing

```powershell
.\release.ps1 -Version <VERSION> -Tag <CODE>
```

Creates a GitHub release with immutable version tag and moving tag for auto-update.

## Configuration

- `config.json` — runtime config with `api_base_url`, optional `api_token` and `api_timeout`
- `deployment.ini` — deployment settings
- Secrets managed via 1Password CLI (`op://VPS/Hardware_API/API_BEARER_TOKEN`)

## Integrations

| Service | Miners | Panel |
|---------|--------|-------|
| Honeygain SDK | BM | Sharing toggle + status |
| Bright SDK | BM (Windows) | Web Indexing toggle + status |
| Mysterium | BM | Node service via NSSM |
| Presearch | BM | Search node status |
| Diiisco | BM | Discovery service |
| Space Acres | SDN | Farm management + Docker |

## External API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/versions/{miner_code}` | GET | Minimum required version |
| `/credentials/{miner_key}` | GET | Key validation + identity |
| `/installations/{miner_key}/installations/{install_id}` | POST | Heartbeat |
| `/installations/{miner_key}/leases/{install_id}` | POST/PATCH | Lease acquire/renew |
| `/installations/{miner_key}/leases/current` | GET | Concurrency check |
| `/PoC/{miner_key}/hardware` | GET/PUT | Hardware status document |

All requests include `Authorization: Bearer <token>` when configured.

## Architecture

The GUI runs unprivileged. Privileged operations (service start/stop, firewall rules) are delegated to a background service via a filesystem IPC queue under `ProgramData/FryNetworks/`.

## Documentation

See [docs/](docs/README.md) for detailed guides:

- **[UAC Removal](docs/README_UAC_Removal.md)** — privilege separation architecture
- **[Service IPC](docs/README_ServiceIPC.md)** — queue-based IPC developer guide
- **[Installer IPC](docs/README_InstallerIPC.md)** — ACL and NSSM setup
- **[GUI Integration](docs/README_GUI_Integration.md)** — config management + visualization
- **[Developer Guide](docs/GUI_DEVELOPER_GUIDE.md)** — IPC API reference and best practices
- **[Service Handoff](docs/SERVICE_HANDOFF.md)** — measurement collection architecture
- **[Integration Configs](docs/integration_config_examples.md)** — JSON schemas for all tools
