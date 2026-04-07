import sys
import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Reward parameters loaded from gui_config.enc (service-managed)
# Defaults to 1.0 base, 0.0 per-tool if not provided by service
# ---------------------------------------------------------------------------
BASE_REWARD = 1.00
PER_TOOL_REWARD = 0.00
BM_BASE_REWARD = 1.00
BM_PER_TOOL_REWARD = 0.00


def load_from_gui_config(multiplier_base: float, multiplier_per_tool: float) -> None:
    """Load reward multipliers from gui_config.enc (service-provided values).
    
    This replaces environment variable defaults and is the single source of truth
    for all reward parameters across all miner types.
    """
    global BASE_REWARD, PER_TOOL_REWARD, BM_BASE_REWARD, BM_PER_TOOL_REWARD
    BASE_REWARD = multiplier_base
    PER_TOOL_REWARD = multiplier_per_tool
    # Keep BM_* synchronized for backwards compatibility
    BM_BASE_REWARD = multiplier_base
    BM_PER_TOOL_REWARD = multiplier_per_tool


def load_from_sdk_config(multiplier_base: float, multiplier_per_tool: float) -> None:
    """Deprecated: Use load_from_gui_config instead."""
    load_from_gui_config(multiplier_base, multiplier_per_tool)
    global BM_BASE_REWARD, BM_PER_TOOL_REWARD
    BM_BASE_REWARD = multiplier_base
    BM_PER_TOOL_REWARD = multiplier_per_tool


def display_pol_indicator(pol_status: bool) -> str:
    """Return UI indicator for PoL status."""
    if pol_status:
        return "✓ Location Verified"  # Green check mark
    else:
        return "⚠ Location Mismatch"  # Yellow/red warning (same as mac mismatch)


def update_rewards_hint(self) -> None:
    """Update rewards multiplier text and footer.

    - Uses the weekly status file to track the current (backend-computed) multiplier.
    - Shows the maximum multiplier possible from the current sharing settings so
      users can immediately see the impact of enabling/disabling tools.
    """
    # For non-BM miners: no bandwidth sharing, multiplier is always 1.0
    # Still need to extract MAC and backend multiplier from weekly status file
    from config_profile import MINER_CODE
    is_bm = (MINER_CODE == "BM")
    
    is_windows = sys.platform.startswith("win")
    h_enabled = bool(self._honeygain_enabled) if (self._allow_honeygain and self._honeygain_enabled is not None) else False
    b_enabled = bool(self._bright_enabled) if (self._allow_bright and self._bright_enabled is not None) else False
    # Treat Mysterium as enabled only when the user toggle is ON.
    if self._allow_mysterium and self.mysterium_panel and hasattr(self.mysterium_panel, "_toggle"):
        try:
            m_enabled = bool(self.mysterium_panel._toggle.isChecked())  # type: ignore[attr-defined]
        except Exception:
            m_enabled = bool(self._mysterium_enabled) if (self._mysterium_enabled is not None) else False
    else:
        m_enabled = bool(self._mysterium_enabled) if (self._allow_mysterium and self._mysterium_enabled is not None) else False

    is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
    mode = self._sharing_mode if is_bm else "none"

    if mode == "none":
        # For non-BM miners, don't assume 1.0 - wait for backend data
        max_multiplier = None
        base_note = "Bandwidth sharing disabled in this build."
        status = "No sharing components available."
    elif mode in ("honeygain", "bright", "mysterium"):
        enabled_flag = h_enabled if mode == "honeygain" else b_enabled if mode == "bright" else m_enabled
        label = {"honeygain": "HG", "bright": "WI", "mysterium": "MYS"}.get(mode, "SHR")
        # Single mode: 1 available tool
        base = BM_BASE_REWARD
        enabled_count = 1 if enabled_flag else 0
        max_multiplier = base + BM_PER_TOOL_REWARD * enabled_count
        if is_mobile:
            per_pct = int(BM_PER_TOOL_REWARD * 100)
            base_note = f"Base rewards {int(base * 100)}% (+{per_pct}% when sharing on)."
            status = f"{label}:{'on' if enabled_flag else 'off'}"
        else:
            pretty = {"honeygain": "Honeygain", "bright": "Web Indexing", "mysterium": "Mysterium"}.get(mode, "Sharing")
            per_pct = int(BM_PER_TOOL_REWARD * 100)
            base_note = f"Base rewards start at {int(base * 100)}%; {pretty} adds +{per_pct}% when enabled."
            status = f"{pretty}: {'enabled' if enabled_flag else 'disabled'}"
    else:
        enabled_count = 0
        components = []
        if h_enabled:
            enabled_count += 1
        components.append(f"HG:{'on' if h_enabled else 'off'}")
        if is_windows and self._allow_bright:
            if b_enabled:
                enabled_count += 1
            components.append(f"WI:{'on' if b_enabled else 'off'}")
        if self._allow_mysterium:
            if m_enabled:
                enabled_count += 1
            components.append(f"MYS:{'on' if m_enabled else 'off'}")

        base = BM_BASE_REWARD

        # Multiplier = base + per-tool bonus per enabled tool
        max_multiplier = base + BM_PER_TOOL_REWARD * enabled_count
        if is_mobile:
            base_pct = int(base * 100)
            per_pct = int(BM_PER_TOOL_REWARD * 100)
            base_note = f"Base {base_pct}% +{per_pct}% each:"
            status = " | ".join(components)
        else:
            base_pct = int(base * 100)
            per_pct = int(BM_PER_TOOL_REWARD * 100)
            base_note = (
                f"Base rewards start at {base_pct}%. Honeygain, Web Indexing, and Mysterium each add +{per_pct}%."
                if is_windows else
                f"Base rewards start at {base_pct}%. Honeygain and Mysterium each add +{per_pct}%."
            )
            status = (
                f"Honeygain: {'enabled' if h_enabled else 'disabled'} | "
                + (f"Web Indexing: {'enabled' if b_enabled else 'disabled'} | " if is_windows and self._allow_bright else "")
                + f"Mysterium: {'enabled' if m_enabled else 'disabled'}"
            )

    # If MAC is still missing (started offline), re-try network discovery.
    if not getattr(self, 'activeMacAddress', None):
        try:
            from miner_GUI.ui.helpers import network as network_helpers
            network_helpers.populate_network_interfaces(self)
        except Exception:
            pass

    # vNext: Prefer the backend-computed multiplier from the weekly status file.
    backend_mult: Optional[float] = None
    try:
        from miner_GUI.utils.status_week import (
            counted_slots_from_day,
            day_doc_from_week,
            load_status_week_for_date,
        )

        today = datetime.datetime.utcnow().date()
        week_doc = load_status_week_for_date(today)
        if isinstance(week_doc, dict):
            # Extract and display MAC information from the weekly doc
            mac_registered = week_doc.get("mac_registered")
            mac_mismatch = week_doc.get("mac_mismatch")

            # Extract and display PoL (Proof of Location) status from the weekly doc
            pol_status = week_doc.get("pol_status")

            # Read verified from weekly JSON (written by service)
            # If not present or False, PoL indicators won't be shown
            verified = week_doc.get("verified", False)
            # Store in self for use by _refresh_footer_status and _refresh_registration_status
            self._verified = verified
            
            # Extract online/pod status from weekly JSON
            # Only null/missing/empty triggers pending
            online_status = week_doc.get("online_status")
            if online_status == "online":
                self._last_pod_ok = True
            elif online_status == "offline":
                self._last_pod_ok = False
            else:
                # None, empty string, or any other non-recognised value — pending gate
                self._last_pod_ok = None

            # Log for debugging
            try:
                from miner_GUI.utils.data import log_step
                log_step("mac_registered_from_week", {
                    "mac_registered": mac_registered,
                    "mac_mismatch": mac_mismatch,
                    "pol_status": pol_status,
                    "verified": verified
                })
            except Exception:
                pass

            # MAC registration display (always shown, not gated by verification)
            # Update the display whether mac_registered is present or not
            try:
                if hasattr(self, "macRegisteredValue"):
                    if mac_registered:
                        self.macRegisteredValue.setText(str(mac_registered))
                    else:
                        # Clear the label if mac_registered is not in JSON
                        self.macRegisteredValue.setText("-")
            except Exception:
                pass

            # MAC match/mismatch styling (always applied, not gated by verification)
            if isinstance(mac_mismatch, bool):
                try:
                    self._style_mac_match(not mac_mismatch)
                except Exception:
                    pass
            else:
                # mac_mismatch is None or missing - set _mac_mismatch to None (keep pending gate)
                # but don't style/show warning (we don't know the status yet)
                self._mac_mismatch = None

            # PoL (Location) state — feeds into unified registration status label
            # When verified=True, location status is shown alongside MAC status
            # When not verified, pol_mismatch is set to None (location hidden)
            if verified is True:
                try:
                    self._update_pol_state(pol_status if isinstance(pol_status, bool) else None)
                except Exception:
                    pass
            else:
                try:
                    self._update_pol_state(None)
                except Exception:
                    pass
            
            day_doc = day_doc_from_week(week_doc, today)
            if isinstance(day_doc, dict) and counted_slots_from_day(day_doc) > 0:
                hours = day_doc.get("hours")
                if isinstance(hours, dict) and hours:
                    best_hour = None
                    for k in hours.keys():
                        try:
                            h = int(k)
                        except Exception:
                            continue
                        if 0 <= h <= 23 and (best_hour is None or h > best_hour):
                            best_hour = h
                    if best_hour is not None:
                        hdoc = hours.get(str(best_hour))
                        if isinstance(hdoc, dict) and "multiplier" in hdoc:
                            try:
                                backend_mult = float(hdoc.get("multiplier", 0.0))
                            except Exception:
                                backend_mult = None
                if backend_mult is None and "avg_multiplier" in day_doc:
                    try:
                        backend_mult = float(day_doc.get("avg_multiplier", 0.0))
                    except Exception:
                        backend_mult = None
            if backend_mult is None:
                week_so_far = week_doc.get("week_so_far")
                if isinstance(week_so_far, dict) and "avg_multiplier" in week_so_far:
                    try:
                        backend_mult = float(week_so_far.get("avg_multiplier", 0.0))
                    except Exception:
                        backend_mult = None
            # Extract week multiplier from backend's pre-calculated value in JSON
            week_so_far = week_doc.get("week_so_far")
            if isinstance(week_so_far, dict) and "avg_multiplier" in week_so_far:
                try:
                    self._week_multiplier = float(week_so_far.get("avg_multiplier", 0.0))
                except Exception:
                    self._week_multiplier = None
            else:
                self._week_multiplier = None
    except Exception:
        backend_mult = None
        self._week_multiplier = None

    # Clamp max for safety and align footer to the active max to avoid stale higher values during enable attempts.
    _abs_max = BM_BASE_REWARD + BM_PER_TOOL_REWARD * 3  # theoretical ceiling (3 tools)
    try:
        safe_max: Optional[float] = max(0.0, min(float(max_multiplier), _abs_max)) if max_multiplier is not None else None
    except Exception:
        safe_max = None

    current_multiplier = backend_mult
    if current_multiplier is not None:
        try:
            current_multiplier = max(0.0, min(float(current_multiplier), _abs_max))
            if safe_max is not None:
                current_multiplier = min(current_multiplier, safe_max)
        except Exception:
            current_multiplier = None
    else:
        # Only use safe_max as fallback if we have actual backend data (week_doc exists)
        # Without backend data, keep None to show "Status pending..." instead of false multiplier
        current_multiplier = None

    self._current_multiplier = current_multiplier
    max_multiplier = safe_max

    # Log for debugging multiplier calculation
    try:
        from miner_GUI.utils.data import log_step
        log_step("update_rewards_hint", {
            "miner_code": MINER_CODE,
            "is_bm": is_bm,
            "mode": mode,
            "backend_mult": backend_mult,
            "safe_max": safe_max,
            "current_multiplier": current_multiplier
        })
    except Exception:
        pass

    # Build final rich text block
    # Max multiplier is shown without gating (online/MAC) to make toggles intuitive.
    badge = self._multiplier_badge(max_multiplier)
    rewards_line = (
        f"Current Max Multiplier: {badge}"
        if badge
        else ("Current Max Multiplier: --" if max_multiplier is None else f"Current Max Multiplier: {max_multiplier:.2f}x")
    )
    if hasattr(self, "rewards_hint"):
        if is_mobile:
            html = f"{base_note} {status}<br><span style='font-size: 13pt; font-weight: bold;'>{rewards_line}</span>"
        else:
            html = f"{base_note} {status}<br><br><span style='font-size: 13pt; font-weight: bold;'>{rewards_line}</span>"
        self.rewards_hint.setText(html)
    try:
        self._refresh_footer_status()
    except Exception:
        pass
