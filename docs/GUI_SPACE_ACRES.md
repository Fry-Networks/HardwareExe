# Space Acres - GUI Integration Guide (SDN)

## Overview

Space Acres is the **Autonomys Network farming** tool for SDN miners. It runs as a Docker Compose stack (node + farmer) and requires the user to select an **SSD drive** and **farm size** before it can be started.

Unlike other tools that only need an enable/disable toggle, Space Acres has a two-step setup: **configure** (pick SSD + size), then **enable** (start Docker containers).

---

## gui_config.enc Schema (SDN)

The service populates `gui_config.enc` with the following SDN-specific fields:

```json
{
  "base_reward": 1.0,
  "per_tool_reward": 0.1,
  "spaceacres": false,
  "available_ssds": [
    { "path": "D:\\", "free_gb": 450.2, "total_gb": 500.0 },
    { "path": "E:\\", "free_gb": 900.7, "total_gb": 1000.0 }
  ],
  "spaceacres_config": {
    "farm_path": "D:\\autonomys-farm",
    "farm_size": "400G"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `spaceacres` | `bool` | Whether Space Acres is approved/enabled (toggle state) |
| `available_ssds` | `list` | SSDs detected by the service at startup. Read-only for GUI |
| `available_ssds[].path` | `string` | Drive root path (Windows: `D:\`, Linux: `/mnt/ssd`) |
| `available_ssds[].free_gb` | `float` | Free space in GiB |
| `available_ssds[].total_gb` | `float` | Total capacity in GiB |
| `spaceacres_config` | `dict` | Farm settings sent by the GUI. Empty `{}` until configured |
| `spaceacres_config.farm_path` | `string` | Full folder path on the selected SSD |
| `spaceacres_config.farm_size` | `string` | Allocated size (e.g. `100G`, `500G`, `1T`) |

---

## UI Components

### 1. Space Acres Toggle

Standard enable/disable toggle, same pattern as presearch/diiisco.

**Visibility rule**: Show only when Docker is available (the service already gates this via `_is_docker_available()`; if `available_ssds` is present in gui_config.enc, Docker is working).

**Disabled state**: If `available_ssds` is empty (no SSDs found), show the toggle greyed out with a tooltip:
> "No SSD drives detected. Space Acres requires an SSD for farming."

### 2. SSD Selection

When the user clicks the toggle ON (or opens Space Acres settings), show the list of available SSDs from `gui_config.enc → available_ssds`.

**Display each SSD as a selectable card/row:**

```
 [D:\]  450.2 GB free / 500.0 GB total
 [E:\]  900.7 GB free / 1000.0 GB total
```

- Pre-select the SSD with the most free space
- Grey out SSDs with less than 100 GB free (minimum for node data + a small farm)
- If only one SSD is available, auto-select it

### 3. Farm Folder Path

After selecting an SSD, show a folder path input pre-filled with a default:

- **Windows**: `{selected_ssd_path}autonomys-farm` (e.g. `D:\autonomys-farm`)
- **Linux**: `{selected_ssd_path}/autonomys-farm` (e.g. `/mnt/ssd/autonomys-farm`)

The user can edit this or browse to a different folder **on the same SSD**.

### 4. Farm Size

Show a slider or input for farm size allocation.

**Constraints:**
- Minimum: `50G`
- Maximum: `available_ssds[selected].free_gb - 100` (reserve 100 GB for node + OS)
- Default: 50% of available free space, rounded to nearest 50G
- Display format: human-readable (e.g. "400 GB", "1.5 TB")
- **Value format sent to service**: string with unit suffix — `100G`, `500G`, `1T`, `2T`

**Size presets** (optional, for convenience):
| Preset | Value | Note |
|---|---|---|
| Small | `100G` | Minimum viable farm |
| Medium | `500G` | Good balance |
| Large | `1T` | Recommended if space allows |
| Maximum | `{max}G` | All available minus 100 GB reserve |

---

## IPC Operations

### Step 1: Configure Farm (before starting)

Send the chosen path and size to the service:

```json
{
  "op": "configure_spaceacres",
  "farm_path": "D:\\autonomys-farm",
  "farm_size": "400G"
}
```

**Response:**
```json
{
  "success": true,
  "op": "configure_spaceacres",
  "request_id": "...",
  "timestamp": "2026-02-24T10:30:00+00:00"
}
```

This writes the config to `gui_config.enc → spaceacres_config`. The service reads it when starting the Docker stack.

**Validation by service:**
- Both `farm_path` and `farm_size` are required (error if missing)
- The service does NOT validate the path exists or is an SSD — the GUI should enforce this from the `available_ssds` list

### Step 2: Enable Space Acres (toggle ON)

Same pattern as presearch/diiisco — write `miner_config.json` with `spaceacres.enabled: true`, then reload:

```python
# 1. Write config
config = {"spaceacres": {"enabled": True}}
send_op({
    "op": "write_config",
    "relative_path": "miner_config.json",
    "content": json.dumps(config)
})

# 2. Reload
send_op({"op": "reload_config"})
```

### Step 3: Start Docker Containers

```json
{
  "op": "start_docker_container",
  "container_name": "spaceacres-node"
}
```

This starts the **entire compose stack** (both `sdn-autonomys-node` and `sdn-autonomys-farmer`). You only need to send `spaceacres-node` — the farmer starts automatically via `depends_on`.

The service runs three phases:
1. Pulls images (`docker compose pull`) — ~840 MB on first run
2. Builds custom images (`docker compose build`) — no-op for Space Acres (pre-built images)
3. Starts containers (`docker compose up -d`) — node starts first, farmer waits for node healthcheck

**Progress feedback:**

During startup the service writes progress updates to:
```
ops_processed/{request_id}.progress.json
```

The GUI should poll this file alongside `{request_id}.done.json` every 500ms.
When `.progress.json` exists, show the phase/detail to the user and extend the
poll timeout to **900 seconds** (first-time image downloads can take minutes).

```json
{
  "request_id": "...",
  "phase": "pulling",
  "detail": "Downloading container images...",
  "updated_at": "2026-02-25T15:21:07+00:00"
}
```

| Phase      | Detail                              | Typical duration     |
|------------|-------------------------------------|----------------------|
| `pulling`  | Downloading container images...     | 1-5 min (cold) / instant (cached) |
| `building` | Building application image...       | instant (no custom build) |
| `starting` | Starting containers...              | 5-60s (node healthcheck) |

**Response (success):**
```json
{
  "success": true,
  "op": "start_docker_container",
  "sync_status_path": "C:\\ProgramData\\FryNetworks\\miner-SDN\\status\\spaceacres_sync.json",
  "initial_status": "syncing"
}
```

> **IMPORTANT**: `success: true` means Docker Compose started successfully, NOT that
> the node is fully synced and ready. When `sync_status_path` is present, the GUI
> **MUST** read that file to determine actual readiness. The `initial_status` field
> gives the status at the moment compose finished (usually `"syncing"` on first start).
> Poll `sync_status_path` every 2-5 seconds until `status` becomes `"running"`.

**Error cases:**
```json
{
  "success": false,
  "error": "Space Acres not configured: FARM_PATH and FARM_SIZE required. Send configure_spaceacres op first."
}
```

### Step 4: Stop (toggle OFF)

```json
{
  "op": "stop_docker_container",
  "container_name": "spaceacres-node"
}
```

This stops both containers (`docker compose down`).

### Setup Firewall (once, on first enable)

```json
{
  "op": "setup_spaceacres_firewall"
}
```

Opens ports:
- **30333/TCP** — Node P2P
- **30433/TCP** — Farmer DSN
- **9944/TCP** — Node RPC (internal)

---

## Complete Flow

```
User opens SDN GUI
    │
    ├── GUI reads gui_config.enc
    │   ├── available_ssds → populate SSD list
    │   ├── spaceacres_config → show current config (if any)
    │   └── spaceacres → toggle state
    │
    ├── User selects SSD + folder + size
    │   └── GUI sends: configure_spaceacres(farm_path, farm_size)
    │
    ├── User flips toggle ON
    │   ├── GUI sends: write_config (spaceacres.enabled = true)
    │   ├── GUI sends: reload_config
    │   ├── GUI sends: setup_spaceacres_firewall  (first time only)
    │   └── GUI sends: start_docker_container(spaceacres-node)
    │
    └── User flips toggle OFF
        ├── GUI sends: stop_docker_container(spaceacres-node)
        ├── GUI sends: write_config (spaceacres.enabled = false)
        └── GUI sends: reload_config
```

---

## Status Display

The service polls Docker container status every measurement cycle. Status is available in `cache/latest.json`:

```json
{
  "selected_tools": ["spaceacres"],
  "spaceacres_stats": {
    "enabled": true,
    "running": true,
    "node_healthy": true,
    "farmer_running": true,
    "status": "running",
    "error": null
  }
}
```

**Status values:**

| `status` | Meaning | Suggested UI |
|---|---|---|
| `running` | Both containers up, synced and finalized | Green indicator |
| `syncing` | Node importing blocks to chain head | Blue indicator + progress bar |
| `finalizing` | Blocks imported, GRANDPA catching up | Blue indicator + "Finalizing..." |
| `degraded` | Container problem (farmer crash-loop) | Orange indicator |
| `stopped` | Containers exist but are stopped | Yellow indicator |
| `not_found` | Containers don't exist yet | Grey indicator |
| `not_created` | Docker not available or never started | Grey indicator, show setup prompt |
| `unknown` | Polling error | Orange indicator |

**Additional fields for detail panel:**

| Field | Type | Description |
|---|---|---|
| `node_healthy` | `bool` | Node container passed healthcheck (synced) |
| `farmer_running` | `bool` | Farmer container is running |
| `error` | `string\|null` | Error message if something went wrong |

---

## Rewards Impact

Space Acres contributes to the SDN parametric reward multiplier:

```
reward = base_reward + per_tool_reward * tool_count
```

- **Without Space Acres**: `tool_count = 0` → user gets `base_reward` only
- **With Space Acres running**: `tool_count = 1` → user gets `base_reward + per_tool_reward`

Show this in the GUI as a reward boost indicator, e.g.:
> "Space Acres active: +{per_tool_reward} reward multiplier"

---

## Important Notes

1. **SSD is mandatory** — HDDs are not supported by Autonomys. The service detects SSDs via hardware queries; only show drives from `available_ssds`
2. **SSDs are scanned every 30 seconds** — but `gui_config.enc → available_ssds` is only updated on significant changes: a drive is added/removed, or free space changes by more than 100 GB. This keeps the list stable for the GUI
3. **Farm data is persistent** — stopping Space Acres does NOT delete farm data. The user keeps their plotted data. Only `docker compose down -v` (not exposed to GUI) would wipe volumes
4. **Initial sync takes time** — the node needs hours to sync the blockchain; the farmer then needs hours/days to plot. Set expectations in the UI
5. **`configure_spaceacres` must be called before `start_docker_container`** — the service validates that `FARM_PATH` and `FARM_SIZE` are set and rejects the start if they're missing
6. **Reward address is embedded at build time** — from 1Password (`op://SDN/SpaceAcres/wallet`). The GUI never sees or sets this
7. **Node name is automatic** — set from the miner key, no user input needed

---

## Blockchain Sync Status

On first start (or after a long offline period), the Autonomys node must sync the blockchain. This can take minutes to hours. During sync, the farmer will not run until the node catches up.

The service writes sync progress to a plain JSON file every 60 seconds:

**Path:** `C:\ProgramData\FryNetworks\miner-SDN\status\spaceacres_sync.json`

```json
{
  "status": "finalizing",
  "node_healthy": true,
  "farmer_running": false,
  "isSyncing": false,
  "currentBlock": 6750575,
  "highestBlock": 6750575,
  "syncPercent": 100.0,
  "finalizedBlock": 6721808,
  "finalizationGap": 28767,
  "peers": 21,
  "error": null,
  "updated_at": "2026-02-26T15:25:00+00:00"
}
```

### Status Values

| `status` | Meaning | Suggested GUI text |
|---|---|---|
| `"syncing"` | Node is importing blocks to reach chain head | "Syncing blockchain: 99.2% (6,733,868 / 6,739,062 blocks)" |
| `"finalizing"` | Blocks imported, GRANDPA finalization catching up | "Finalizing: {finalizationGap} blocks remaining" |
| `"running"` | Fully synced, finalized, and farming | "Running - Fully synced" |
| `"degraded"` | Container problem (not sync-related) | "Degraded - check logs" |
| `"stopped"` | Containers exist but not running | "Stopped" |
| `"not_created"` | No containers found | "Not configured" |
| `"docker_missing"` | Docker not installed | "Docker not available" |

> **Note on finalization**: The Autonomys node has two sync phases. First, it imports
> blocks to reach chain head (`isSyncing=true` → `false`, `syncPercent` goes to 100%).
> Then GRANDPA consensus must finalize those blocks (`finalizationGap` shrinks toward 0).
> The farmer **cannot start** until finalization is close to chain head. A gap > 100
> blocks means the node is still finalizing.

### GUI Polling

- Poll `spaceacres_sync.json` every 2-5 seconds while the Space Acres panel is visible
- File is updated by the service every ~60 seconds
- When `isSyncing` is `null`: RPC not reachable yet (node still starting), show "Starting node..." or Docker container status only
- When `status` is `"syncing"`: show a progress bar using `syncPercent` and display `currentBlock` / `highestBlock`
- When `status` transitions from `"syncing"` to `"running"`: show success notification

---

## Network Ports

Tell users to forward these ports on their router for optimal performance:

| Port | Protocol | Purpose |
|---|---|---|
| 30333 | TCP | Node peer-to-peer |
| 30433 | TCP | Farmer DSN (Distributed Storage Network) |
| 9944 | TCP | Node RPC (localhost only, not exposed externally) |

---

## File Paths

```
C:\ProgramData\FryNetworks\miner-SDN\
├── config/
│   ├── space_acres_config.json ← spaceacres enabled toggle
│   └── gui_config.enc          ← available_ssds + spaceacres_config (encrypted)
├── status/
│   └── spaceacres_sync.json    ← Blockchain sync progress (plain JSON, updated every 60s)
├── ops_queue/                  ← Send IPC requests here
├── ops_processed/              ← Read IPC responses here
└── logs/
    └── service.err.log         ← Debug
```

Linux equivalent: `/opt/FryNetworks/miner-SDN/`
