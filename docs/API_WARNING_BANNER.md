# API Availability Warning Banner Implementation

## Overview
The GUI now displays a warning banner when the Hardware API is unavailable, informing users that while their miner continues to work and collect data locally, reward syncing will resume when the backend API recovers.

## Changes Made

### 1. Weekly JSON Schema Update
The weekly status JSON file now includes two new fields:
- `api_available` (boolean): Indicates whether the Hardware API is reachable
- `api_last_updated` (timestamp): When the API status was last checked

Example:
```json
{
  "miner_key": "AEM-...",
  "docker": true,
  "api_available": false,
  "api_last_updated": "2026-02-11T10:30:00Z",
  ...
}
```

### 2. GUI Implementation ([main_window.py](miner_GUI/ui/main_window.py))

#### State Variable
- Added `_api_available: bool = True` to track API availability state (line ~141)
- Added `api_warning_banner: Optional[QtWidgets.QWidget] = None` widget reference (line ~165)

#### Warning Banner Widget
- Created `_create_api_warning_banner()` method (line ~543) that:
  - Creates a prominent orange warning banner
  - Displays warning icon and informative message
  - Initially hidden until API becomes unavailable
  - Styled with high-visibility colors (#FF9800 background, #F57C00 border)

#### Layout Integration
- Banner is created during UI initialization (line ~480)
- Added to main layout immediately after the main banner (line ~1721)
- Positioned prominently at top of window for maximum visibility

#### Data Polling Updates
- **AEM Live Data Polling** (`_poll_aem_live_data`, line ~2283):
  - Reads `api_available` from weekly JSON along with `mac_mismatch`
  - Passes value to `_update_live_data()`

- **Generic Live Data Polling** (`_poll_live_data`, line ~2267):
  - Also reads `api_available` from weekly JSON for all miner types (BM, IDM, ISM, etc.)
  - Ensures banner works across all hardware configurations

#### Banner Display Logic
- Created `_update_api_warning_banner()` method (line ~2403) that:
  - Shows banner when `api_available` is explicitly `False`
  - Hides banner when `api_available` is `True` or `None` (unknown)
  - Updates internal `_api_available` state
  - Handles exceptions gracefully

- Updated `_update_live_data()` method (line ~2421):
  - Calls `_update_api_warning_banner()` when `api_available` is present in data
  - Processes API status before other live data updates

### 3. Sample Fixtures
Updated documentation fixtures:
- [status-week-sample.json](docs/fixtures/status-week-sample.json): Shows normal operation with `api_available: true`
- [status-week-api-down-sample.json](docs/fixtures/status-week-api-down-sample.json): Shows API outage scenario with `api_available: false`

## User Experience

### When API is Available (Normal)
- Warning banner is hidden
- GUI operates normally
- No visual indication of API status

### When API is Unavailable
- Orange warning banner appears below main banner
- Message displays: "**Hardware API Unavailable** — Your miner is still working and collecting data locally. Reward syncing will resume automatically when the backend API recovers."
- Warning icon (⚠️) draws attention
- Banner remains visible until API recovers

## Technical Details

### Banner Styling
```python
#apiWarningBanner {
    background-color: #FF9800;  # Orange background
    border: 2px solid #F57C00;  # Darker orange border
    border-radius: 4px;
    color: #000000;             # Black text for contrast
}
```

### Polling Frequency
- API status is checked every polling cycle (typically 15-30 seconds)
- Updates are asynchronous and non-blocking
- No impact on measurement collection

### Compatibility
- Works with all miner types (AEM, BM, IDM, ISM, IRM, OSM, ODM, RDN, SDN, SVN)
- Backward compatible (gracefully handles missing `api_available` field)
- No breaking changes to existing functionality

## Testing

To test the warning banner:
1. Copy `docs/fixtures/status-week-api-down-sample.json` to your data directory as the current week's status file
2. Launch the GUI
3. Verify the orange warning banner appears below the main banner
4. Update the file to set `api_available: true`
5. Verify the banner disappears within one polling cycle

## Implementation Notes

- The banner uses Qt's show/hide methods for smooth transitions
- Banner visibility is controlled entirely by the `api_available` field value
- `None` or missing field is treated as "unknown" and banner stays hidden
- Only explicitly `False` triggers the warning banner
- Banner height and spacing automatically adjust to window layout
