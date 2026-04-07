# GUI Dynamic Texts and Banners

This document lists all dynamic texts, banners, status messages, and notifications that can appear in the miner GUI.

---

## 1. Global Constants

| Text | Location | Condition |
|------|----------|-----------|
| `⏳ Waiting for miner to be fully configured...` | All tool panels | When any **top-level** gate is unknown (`mac_mismatch=None` OR `online_status="unknown"` at root of weekly JSON, NOT within `days` object) |

---

## 2. Warning Banners

| Text | Location | Condition | Priority |
|------|----------|-----------|----------|
| `⚠ Status Data Is Stale — The local status file has not been updated in {X} minutes. The miner service may need attention.` | Top banner | When `lastUpdated` timestamp is >15 minutes old | Highest (1) |
| `⚠ API Temporarily Unavailable` | Top banner | When `api_available=false` OR `api_last_updated` is >15 minutes old (hidden if Stale banner is showing) | Lower (2) |

**Banner Priority Logic:** Stale banner takes precedence over API banner. When stale banner is showing, API banner is hidden to avoid banner overload.

---

## 3. Footer Status Texts

| Text | Icon | Condition |
|------|------|-----------|
| `Status pending...` | ● (gray) | When `mac_mismatch=None` OR `online_status=None` |
| `Device online` | ✓ (green) | When `_last_pod_ok=True` and no mismatch |
| `Device offline` | ⚠ (orange) | When `_last_pod_ok=False` |
| `Device offline - {error}` | ⚠ (orange) | When `_last_pod_ok=False` with error message |
| `Registration mismatch` | ⚠ (orange) | When MAC or PoL mismatch exists |

**Footer also shows:**
- `Current Rewards Multiplier: {X.XX}x` with badge
- `Week Multiplier: {X.XX}x` with badge
- Hardware stats (CPU/RAM usage)

---

## 4. MAC/Registration Status

| Text | Location | Condition |
|------|----------|-----------|
| `✔ MAC match` | MAC status label | When MAC matches registered |
| `⚠ MAC mismatch — Please update your registration in the Fry Networks dashboard.` | MAC status label | When MAC doesn't match |
| `⚠ MAC mismatch — Please update your registration in the Fry Networks dashboard before enabling this tool.` | Tool panel warning | When trying to enable tool with MAC mismatch |

---

## 5. PoL (Proof of Location) Status

| Text | Location | Condition |
|------|----------|-----------|
| `✓ Location Verified` | PoL status label | When `pol_status=true` and `verified=true` |
| `⚠ Location Mismatch` | PoL status label | When `pol_status=false` and `verified=true` |
| `❓ Location Status Unknown` | PoL status label | When `pol_status=null/missing` and `verified=true` |

**Note:** PoL indicators are only shown when `verified=true`. Otherwise they are hidden.

---

## 6. Tooltips

| Text | Element |
|------|---------|
| `Active MAC differs from the registered MAC. Open your Fry Networks dashboard and update the device registration to the current MAC address.` | MAC mismatch icon |
| `Active MAC matches your registered MAC address.` | MAC match icon |
| `Your registered location matches your current location.` | PoL match icon |
| `Your registered location doesn't match your current location.` | PoL mismatch icon |

---

## 7. Honeygain Panel

| Text | Condition |
|------|-----------|
| `Honeygain status: unavailable` | Initial state |
| `Honeygain SDK not available` | SDK not loaded |
| `Honeygain installer data missing` | Not configured |
| `Honeygain is disabled. Enable it to add a +{X}% boost to your base rewards!` | Disabled |
| `Great! Honeygain is enabled and adding a +{X}% boost to your base rewards.` | Running |
| `Honeygain waiting for consent` | Enabled but `opted_in=False` |
| `Honeygain enabled but not running` | Enabled, not running |

---

## 8. Bright (Web Indexing) Panel

| Text | Condition |
|------|-----------|
| `Bright SDK status: unavailable` | Initial state |
| `Bright SDK not available (Windows only)` | SDK not loaded |
| `Bright installer data missing` | Not configured |
| `Web Indexing is disabled. Enable it to add a +{X}% boost to your base rewards!` | Disabled |
| `Great! Web Indexing is enabled and adding a +{X}% boost to your base rewards.` | Running |
| `Web Indexing enabled but not running` | Enabled, not running |

---

## 9. Mysterium Panel

| Text | Condition |
|------|-----------|
| `Mysterium status: unavailable` | Initial state |
| `Mysterium is disabled. Enable it to add a +{X}% boost to your base rewards!` | Disabled |
| `Great! Mysterium is enabled and adding a +{X}% boost to your base rewards.` | Running |
| `Mysterium enabled \| API port unreachable` | Port not OK |
| `Mysterium enabled \| API not responding` | API not OK |
| `Mysterium is enabled.` | Enabled, not running |
| `{status} \| Status check failed - showing last known state` | API check failed |

---

## 10. Presearch Panel

| Text | Condition |
|------|-----------|
| `Presearch Node status: unavailable` | Initial state |
| `Docker is not installed or not running. Please install and start Docker to enable Presearch.` | `docker=false` in weekly JSON |
| `Unable to determine Docker status. Please check that the miner service is running.` | `docker=null/missing` in weekly JSON |
| `Presearch Node not configured. Get registration code from presearch.io` | Not configured |
| `Connected` | Running + connected |
| `Running (connecting...)` | Running, not connected |
| `Stopped` | Not running |
| `Error: {error}` | Has error |
| `Status unknown` | Fallback |

**Stats displayed:**
- `PRE Earned: {X}`
- `Reliability: {X}%`
- `Uptime: {X} days` or `{X} hrs`
- `Queries today: {X}`
- `Node: {id}`

---

## 11. Space Acres Panel

| Text | Condition |
|------|-----------|
| `Space Acres status: unavailable` | Initial state |
| `Space Acres not configured. Install from docs.autonomys.xyz` | Not configured |
| `Farming active` | Running + farming |
| `Syncing blockchain` | Running + syncing |
| `Running` | Running |
| `Stopped` | Not running |
| `Node connecting...` | Running, node not connected |
| `Error: {error}` | Has error |
| `Status unknown` | Fallback |

**Stats displayed:**
- `Plotted: {X} GB`
- `Block: #{X}`
- `Rewards: {X} tSSC`

---

## 12. Diiisco Panel

| Text | Condition |
|------|-----------|
| `Diiisco Node status: unavailable` | Initial state |
| `Diiisco Node not configured. Visit github.com/FrysCrypto/diiisco-node` | Not configured |
| `Connected` | Running + connected |
| `Running (connecting...)` | Running, not connected |
| `Stopped` | Not running |
| `Network: {network}` | Has network info |
| `Error: {error}` | Has error |
| `Status unknown` | Fallback |

**Stats displayed:**
- `Peers: {X}`
- `Discoveries: {X}`
- `Uptime: {X} hrs`

---

## 13. Rewards/Multiplier Texts

| Text | Condition |
|------|-----------|
| `Bandwidth sharing disabled in this build.` | mode="none" |
| `No sharing components available.` | mode="none" |
| `Base rewards {X}% (+{Y}% when sharing on).` | Single sharing mode (mobile) |
| `Base rewards start at {X}%; {Tool} adds +{Y}% when enabled.` | Single sharing mode (desktop) |
| `Base {X}% +{Y}% each:` | Multi-tool mode (mobile) |
| `Base rewards start at {X}%. Honeygain, Web Indexing, and Mysterium each add +{Y}%.` | Multi-tool mode (desktop, Windows) |
| `Base rewards start at {X}%. Honeygain and Mysterium each add +{Y}%.` | Multi-tool mode (desktop, non-Windows) |

**Tool status summary:**
- Mobile: `HG:on/off | WI:on/off | MYS:on/off`
- Desktop: `Honeygain: enabled/disabled | Web Indexing: enabled/disabled | Mysterium: enabled/disabled`

---

## 14. Disable Sharing Confirmation Dialog

| Text | Element |
|------|---------|
| `Disable {service_label} Sharing?` | Dialog title |
| `Turning off {service_label} will reduce your base fVPN rewards by {X}%. Are you sure you want to disable it?` | Dialog message |

---

## 15. System Tray

| Text | Condition |
|------|-----------|
| `{MINER_CODE} Miner` | Tray icon tooltip |
| `Running in background. Right-click tray icon to Exit.` | Window minimized notification |

---

## 16. Rewards History Widget

| Text | Condition |
|------|-----------|
| `✓ All good` | No issues found |
| `{Tool}: Not active` | Tools not fully active |
| `{Issue}: {X}x` | Issue count display |
| `Service: ⚠` | Service warning status |

---

## 17. Multiplier Badges

| Badge | Multiplier Range | Color |
|-------|------------------|-------|
| ★★★ | ≥1.30 | Gold (#FFD700) |
| ★★ | ≥1.15 | Silver (#C0C0C0) |
| ★ | ≥1.01 | Bronze (#CD7F32) |
| ○ | <1.01 | Gray (#6B7280) |

---

## 18. Connection Status Badges

| Text | Color | Condition |
|------|-------|-----------|
| `Online` | Emerald (#059669) | `_last_pod_ok=True` |
| `Offline` | Red (#DC2626) | `_last_pod_ok=False` |
| `Unknown` | Gray (#374151) | `_last_pod_ok=None` |

---

## 19. Error/Placeholder Texts

| Text | Location | Condition |
|------|----------|-----------|
| `Logo Unavailable` | Logo area | Logo load failure (unsupported format) |
| `Logo Not Found` | Logo area | Logo file missing |
| `Logo Error` | Logo area | Logo load exception |
| `Chart unavailable` | Rewards history | Chart creation failure |
| `Live data not available for this miner type` | Live panel | Non-LiveData miners |
| `DL: - Mbps` / `UL: - Mbps` | Bandwidth display | Initial/no data |
| `N/A` | Various | Missing data |
| `--` | Summary cards | No data available |

---

## Key Files Reference

| File | Content |
|------|---------|
| `main_window.py` | Main UI, banners, footer, MAC/PoL status, dialogs |
| `honeygain_panel.py` | Honeygain status messages |
| `bright_panel.py` | Bright/Web Indexing status messages |
| `mysterium_panel.py` | Mysterium status messages |
| `presearch_panel.py` | Presearch status messages |
| `space_acres_panel.py` | Space Acres status messages |
| `diiisco_panel.py` | Diiisco status messages |
| `rewards.py` | Rewards multiplier texts, PoL indicator |
| `measurement_display.py` | PoD badge texts |
| `rewards_history.py` | History widget status |
