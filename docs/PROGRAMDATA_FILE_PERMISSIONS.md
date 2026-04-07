# ProgramData Files & Write Permissions Analysis

## Critical Issue Summary

The GUI writes JSON and CSV files to **`C:\ProgramData\FryNetworks\miner-{CODE}\`**, which is a system-protected directory requiring admin privileges. The current UAC elimination implementation delegates firewall operations but **does NOT address config file writes**.

**User mode cannot write to ProgramData without admin privileges.**

---

## Files Written to ProgramData

### 1. Configuration Files (JSON)
Located: `C:\ProgramData\FryNetworks\miner-{CODE}\config\`

| File | Purpose | Module | Operation | Privilege Level |
|------|---------|--------|-----------|-----------------|
| `device_config.json` | Audio/serial device settings | `miner_GUI/utils/device_config.py` | Read/Write (atomic) | **ADMIN REQUIRED** |
| `honeygain.json` | Honeygain SDK settings | `miner_GUI/services/honeygain.py` | Read/Write (.persist()) | **ADMIN REQUIRED** |
| `bright.json` | Bright SDK settings | `miner_GUI/services/bright.py` | Read/Write (.persist()) | **ADMIN REQUIRED** |
| `presearch.json` | Presearch node settings | `miner_GUI/services/presearch.py` | Read/Write (.persist()) | **ADMIN REQUIRED** |
| `space_acres.json` | Space Acres settings | `miner_GUI/services/space_acres.py` | Read/Write (.persist()) | **ADMIN REQUIRED** |
| `diiisco.json` | Diiisco node settings | `miner_GUI/services/diiisco.py` | Read/Write (.persist()) | **ADMIN REQUIRED** |

### 2. Status/Measurement Files (JSON)
Located: `C:\ProgramData\FryNetworks\miner-{CODE}\status\` and `measurements\`

| File | Purpose | Module | Operation | Privilege Level |
|------|---------|--------|-----------|-----------------|
| `status-YYYYMMDD.json` | Daily status/earnings | `miner_GUI/services/mysterium.py:L1555-1580` | Read/Modify/Write | **ADMIN REQUIRED** |
| `status-rolling7.json` | 7-day rolling data | `rolling_days.py` | Read/Write (atomic) | **ADMIN REQUIRED** |
| `measurements-{GROUP}-latest.json.enc` | (Legacy) Encrypted measurement data | Removed from GUI (service writes CSV logs) | n/a | n/a |

### 3. Key/Registration Files
Located: `C:\ProgramData\FryNetworks\miner-{CODE}\`

| File | Purpose | Module | Operation | Privilege Level |
|------|---------|--------|-----------|-----------------|
| `keystore.json` | Mysterium identity keys | `miner_GUI/services/mysterium.py:L229-237` | Write (.write_bytes()) | **ADMIN REQUIRED** |
| `.registered` | Registration marker | `miner_GUI/services/mysterium.py:L286, L306` | Write (.write_text()) | **ADMIN REQUIRED** |

---

## Read Operations (User-Mode Safe)

The following operations **do NOT require admin**:
- Reading encrypted config files (`miner_config.enc`)
- Reading JSON status files (read-only queries)
- Reading device configuration (read-only display)
- Reading SDK location from config

Write operations are the critical issue.

---

## Root Cause Analysis

### Why ProgramData?

```python
# From miner_GUI/utils/data.py:L44-47
def data_dir_gui() -> Path:
    """Get the GUI data directory (ProgramData on Windows, /var/lib on Linux)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / "FryNetworks" / f"miner-{MINER_CODE}"
```

**Reasons for ProgramData location:**
1. **System-wide data** - Multiple users on same machine should see same config
2. **Persistent across GUI restarts** - Service and GUI share state
3. **Service access** - Service running as SYSTEM reads these files
4. **Standardized location** - Windows convention for app data

**Problem:** ProgramData has restricted write permissions by default:
```
C:\ProgramData\        [System: Full, Administrators: Full, Users: Read only]
```

---

## Current Implementation Gaps

### What the UAC Elimination DOES handle:
✅ Firewall rule creation (delegated to service)  
✅ Process termination with force-kill (delegated to service)

### What it DOES NOT handle:
❌ Config file writes (honeygain.json, bright.json, etc.)  
❌ Status file updates (status-YYYYMMDD.json)  
❌ Device config persistence (device_config.json)  
❌ Measurement file writes (legacy encrypted `.enc` files) — removed from GUI; service writes CSV under `logs/`  
❌ Keystroke and registration markers

---

## Solution Options

### **Option A: Delegate All Writes to Service** (Recommended)

Extend `privileged_ops.py` to handle all ProgramData writes. GUI requests via function calls; service performs writes.

**Pros:**
- Consistent with firewall implementation
- No app code changes to access paths
- Service maintains data integrity
- Single authority over system files

**Cons:**
- Larger `privileged_ops` module (add 200+ lines)
- More service communication overhead
- Requires versioning for config changes

**Implementation:**
```python
# Add to privileged_ops.py
def write_config_file(relative_path: str, content: str) -> Tuple[bool, str]:
    """Write JSON config to ProgramData."""
    
def read_config_file(relative_path: str) -> Tuple[bool, str, str]:
    """Read JSON config from ProgramData."""
    
def write_measurement(group: str, encrypted_data: bytes) -> Tuple[bool, str]:
    """Write encrypted measurement data."""
```

**Service startup:**
```powershell
nssm set <ServiceName> AppPreStart "python -m miner_GUI.services.privileged_ops --setup-startup"
```

### **Option B: User-Writable Local Directory**

Store GUI-owned files in `%LOCALAPPDATA%\FryNetworks\` (user-writable), keep ProgramData for service-only files.

**Pros:**
- No admin needed for GUI writes
- GUI/service can operate independently
- Simpler immediate implementation

**Cons:**
- Data not shared across users on same machine
- Service needs two locations to read state
- Breaks "system-wide" design intent
- Config duplication/sync issues

**File layout:**
```
C:\Users\{User}\AppData\Local\FryNetworks\miner-{CODE}\
  ├── config\               (GUI-writable copies)
  │   ├── device_config.json
  │   ├── honeygain.json
  │   └── bright.json
  └── status\
      ├── status-rolling7.json
      └── measurements\

C:\ProgramData\FryNetworks\miner-{CODE}\
  ├── config\               (Service-only, installer-written)
  └── status\               (Service-only)
```

### **Option C: Elevate GUI Temporarily for Writes** (Not Recommended)

Retain old UAC prompt, but only on startup and when writing configs.

**Pros:**
- Minimal code changes
- Easy to implement

**Cons:**
- Defeats purpose of UAC elimination
- UAC prompt returns for every config change
- Poor user experience

### **Option D: Hybrid Approach**

Use Option B (LOCALAPPDATA) for GUI state, Option A (service) for ProgramData synchronization.

**Pros:**
- GUI works without admin
- Service still has authority
- State shared across users via periodic sync

**Cons:**
- Most complex implementation
- Requires sync logic
- Potential race conditions

---

## Recommendation: **Option A (Delegate to Service)**

**Why:** Consistent architecture, maintains single authority, minimal app code changes.

### Implementation Steps

#### Step 1: Extend `privileged_ops.py` (150+ lines)

```python
def write_config_file(
    relative_path: str,
    content: str,
    create_dirs: bool = True
) -> Tuple[bool, str]:
    """Write JSON config file to ProgramData.
    
    Args:
        relative_path: Path relative to C:\ProgramData\FryNetworks\miner-{CODE}\
                      e.g., "config/device_config.json"
        content: JSON string content
        create_dirs: Whether to create parent directories
        
    Returns:
        (success, message)
    """
    
def write_measurement_file(
    group: str,
    encrypted_data: bytes
) -> Tuple[bool, str]:
    """Write encrypted measurement to ProgramData.
    
    Args:
        group: Measurement group ID
        encrypted_data: Already-encrypted bytes from Fernet
        
    Returns:
        (success, message)
    """
    
def read_config_file(
    relative_path: str
) -> Tuple[bool, str, Optional[str]]:
    """Read JSON config from ProgramData.
    
    Returns:
        (success, message, content) where content is file text
    """
```

#### Step 2: Update Config Modules

Modify all `.persist()` methods to delegate:

**Before:**
```python
def persist(self) -> None:
    with open(self.path, "w", encoding="utf-8") as f:
        json.dump(self._raw, f, indent=2)
```

**After:**
```python
def persist(self) -> None:
    from miner_GUI.services import privileged_ops
    content = json.dumps(self._raw, indent=2)
    success, msg = privileged_ops.write_config_file(
        relative_path=self.path.relative_to(data_dir_gui()),
        content=content
    )
    if not success:
        log_step("config_persist_failed", {"error": msg})
        # Optionally raise or return False
```

#### Step 3: Update Status File Writes

```python
# In mysterium.py:L1579-1580
# Instead of:
# with open(json_path, "w", encoding="utf-8") as f:
#     json.dump(data, f, indent=2)

# Use:
from miner_GUI.services import privileged_ops
success, msg = privileged_ops.write_config_file(
    relative_path=json_path.relative_to(data_dir_gui()),
    content=json.dumps(data, indent=2)
)
```

---

## Testing Checklist

### Pre-Implementation
- [ ] Identify all file write locations (completed above)
- [ ] Verify service has access to ProgramData
- [ ] Test `privileged_ops` module with mock writes

### Post-Implementation
- [ ] GUI can change device config without admin ✅ (non-blocking)
- [ ] GUI can save SDK settings without admin ✅ (honeygain, bright, etc.)
- [ ] Status files update correctly ✅ (no GUI UAC needed)
- [ ] Measurements write successfully ✅ (service reads them)
- [ ] Service can read all modified files ✅ (permissions verified)
- [ ] GUI behavior unchanged when writes fail (graceful fallback)
- [ ] Upgrade scenario: old status/config files preserved

### Functional Testing
```bash
# Verify no permission errors
tasklist | findstr "miner_GUI"
# Change device config via GUI → Should succeed without admin

# Verify service can read updates
nssm status <ServiceName>  # Should show running
# Check logs for successful config reads
```

---

## Migration Path

### Phase 1: Firewall Operations (✅ DONE)
- Add firewall rules via service
- GUI doesn't need admin for firewall setup

### Phase 2: File Write Operations (→ NEXT)
- Add file I/O to `privileged_ops`
- Delegate config writes from GUI to service
- Update all `.persist()` methods
- Update status file writes


### Phase 3: Validation
- Integration test in sandbox
- Verify no UAC prompts during normal operation
- Verify old UAC code is completely removed

---

## Files That Need Modification

| File | Changes | Lines |
|------|---------|-------|
| `miner_GUI/services/privileged_ops.py` | Add write_config_file(), write_measurement_file(), read_config_file() | +150 |
| `miner_GUI/services/bright.py` | Update persist() to delegate | ~5 |
| `miner_GUI/services/honeygain.py` | Update persist() to delegate | ~5 |
| `miner_GUI/services/presearch.py` | Update persist() to delegate | ~5 |
| `miner_GUI/services/space_acres.py` | Update persist() to delegate | ~5 |
| `miner_GUI/services/diiisco.py` | Update persist() to delegate | ~5 |
| `miner_GUI/utils/device_config.py` | Update write_device_config() to delegate | ~10 |
| `miner_GUI/services/mysterium.py` | Update status file writes to delegate | ~10 |
| `rolling_days.py` | Update file writes to delegate | ~5 |
**Total new code:** ~150 lines (privileged_ops)  
**Total modified:** ~55 lines (across 8 files)

---

## Summary

The current implementation successfully eliminates UAC for **firewall operations** but leaves **ProgramData file writes unresolved**. The GUI will still encounter permission errors when:

1. User changes device audio/serial settings
2. User enables/disables Honeygain, Bright, or other services
3. System updates daily status logs
4. Service writes encrypted measurements (legacy path; removed from GUI)

**Next step:** Extend `privileged_ops` to handle file I/O operations, delegating all ProgramData writes to the service (Option A). This maintains architectural consistency and removes admin requirement for all GUI operations.
