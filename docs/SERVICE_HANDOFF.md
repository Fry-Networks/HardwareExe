# Service Handoff: Measurements Collection, CSV Output, and Tools Integration

This document is the implementation guide for the autonomous service. It clarifies responsibilities, storage formats, polling intervals, and SDK/tool integration so the GUI remains display + configuration only.

---

## Summary
- **Authoritative storage:** Daily CSV files per sensor in `%PROGRAMDATA%/FryNetworks/miner-{CODE}/measurements/`. GUI reads these CSVs for Live Data and Data History.
- **JSON deprecation:** The GUI **no longer consumes** `measurements/latest.json`. Keeping it is optional for external tooling, but it is not required by the GUI.
- **Terminology:** We refer to integrations as **tools** (Mysterium, Bright, Honeygain, Presearch, SpaceAcres, Diiisco), not PoC.
- **Service role:** Collect data on a schedule, append rows to daily CSVs, optionally mirror a compact `latest.json`, and (next phase) send data to backend.

---

## Responsibilities
- **Service (autonomous):**
  - Collect sensor data on configured intervals.
  - Write append-only **daily CSV** files per sensor/tool.
  - Optionally mirror a simplified `latest.json` for external consumers.
  - Prepare for backend POST sender (real-time) — stub exists; implementation forthcoming.
- **GUI (display + config only):**
  - Poll last row from CSV for Live Data panels.
  - Load full CSV for Data History.
  - Provide device/config UI (serial ports, audio devices, tool toggles).

---

## CSV Output (Authoritative)
- **Location:** `%PROGRAMDATA%\FryNetworks\miner-{CODE}\measurements\{sensor}_YYYYMMDD.csv`
- **Encoding:** UTF-8 (no BOM). Append-only. One header row.
- **Rotation:** New file per calendar day (YYYYMMDD).
- **Writer:** Use `miner_GUI/services/service_csv_writer.py` (`append_row()`), even in service context.

### CSV Schemas per Sensor/Tool
- **Bandwidth (BM/IDM/ODM):**
  - Columns: `timestamp,dl,ul,iface`
  - Values: Mbps (floats), interface string
- **Satellite (ISM/OSM):**
  - Columns: `timestamp,sats,fix,hdop,lat,lon`
  - Values: integers/floats; `fix` = NONE/GPS/DGPS/etc.
- **Radiation (IRM):**
  - Columns: `timestamp,cpm,usv,mr`
- **Decibel (IDM/ODM):**
  - Columns: `timestamp,dbfs`
- **Tools (integrations):**
  - **Mysterium:** `timestamp,online,earnings_usd,sessions`
  - **Honeygain:** `timestamp,enabled,earnings_usd,status`
  - **Bright:** `timestamp,enabled,status`
  - **Presearch/SpaceAcres/Diiisco:** `timestamp,online,earnings_usd,status`

---

## Collection Intervals (Service Scheduler)
- **Bandwidth:** 2–10 seconds (adapter stats). Real bandwidth test every 10 minutes.
- **Satellite:** 10 seconds.
- **Radiation:** 10 seconds.
- **Decibel:** 2 seconds.
- **Tools (Mysterium, Honeygain, Bright, Presearch, SpaceAcres, Diiisco):** 60 seconds.

Implement these timers in the service entrypoint (e.g., `miner_online_simple.py` or dedicated service main). Each tick:
- Sample → build row dict → `append_row(sensor_type, row)` → (optional) update compact `latest.json` → (future) POST to backend.

---

## JSON (latest.json) — Status
- **Not used by GUI.** The GUI reads CSV only.
- **Keep optional** if external tools depend on it; treat as a simplified mirror of current state.
- **Plan to deprecate** once all consumers transition to CSV/HTTP.

---

## SDK & Tools Integration Notes (Bright, Honeygain)
- **Configuration files:**
  - Bright: `%PROGRAMDATA%/FryNetworks/miner-{CODE}/config/bright.json`
  - Honeygain: `%PROGRAMDATA%/FryNetworks/miner-{CODE}/config/honeygain.json`
  - Secrets are provided via encrypted artifacts (existing CLI tooling) and decrypted on start.
- **Service responsibilities:**
  - Initialize and manage SDK processes (start/stop/restart) according to config/toggles.
  - Detect status/health from SDK (running, errors, version mismatch, authentication state).
  - **Write CSV rows** at 60s intervals reflecting status and earnings where applicable.
  - Handle retries/backoff and log actionable errors.
- **Error handling:**
  - If SDK binaries are missing or misconfigured, emit status rows with `enabled=false` or `status=error` and log details.
  - Avoid blocking the main service loop; isolate SDK calls with timeouts.

---

## Implementation Checklist (Service)
- **Collectors:**
  - Implement samplers for bandwidth, satellite (serial/NMEA), radiation (serial), decibel (audio), and tools.
- **CSV writer:**
  - Route all samples through `service_csv_writer.append_row()` with stable headers.
- **Scheduler:**
  - Add per-sensor timers with graceful shutdown control.
- **Backend sender (next phase):**
  - Use `requests` to POST measurements as they are collected (batch or immediate). Include retry/backoff.
- **Observability:**
  - Log errors and key events; include minimal health telemetry (last write time per sensor).

---

## Testing Guidance
- **Seed CSVs** for multiple days to validate date navigation; confirm GUI charts and Live Data update.
- **Verify BOM-free files** (readers tolerate BOM, but writers must not emit it).
- **Cross-miner validation:** IDM/ISM/IRM/AEM Live Data + Data History functional.

---

## Migration Notes
- **GUI:** Fully decoupled from collection; no writes.
- **Service:** Be the single source of truth for measurements.
- **latest.json:** Transitional only; will be phased out after external consumers move to CSV/HTTP.

---

## Deliverables for Service Team
- Implement scheduler + collectors.
- Write daily CSVs per sensor/tool (schemas above).
- Integrate Bright/Honeygain SDKs as described and emit status CSV rows.
- Prepare backend sender (HTTP) hook for the next phase.
