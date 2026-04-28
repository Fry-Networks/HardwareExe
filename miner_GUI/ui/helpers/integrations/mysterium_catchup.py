"""Mysterium TOS catch-up handler for GUI startup.

Called before init_mysterium_support() to ensure TOS consent is resolved.
Handles three cohorts:
  - Cohort A (existing fleet, TequilAPI agreed_provider=true): silent pass
  - Cohort B (no prior consent, or pending catch-up): shows consent dialog
  - Already-resolved (tos_state.json present with non-declined, non-pending): skip

Critical for Track 1.8 fix: when TOS is resolved AND daemon is already
running (post-install-time provisioning), this function sets
``window._mysterium_enabled = True`` so that init_mysterium_support() →
_on_status_ready() picks up the flag and shows the panel as enabled WITHOUT
dispatching the setup worker or showing a progress dialog.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from miner_GUI.utils.tos_state import (
    is_resolved_accept,
    read_tos_state,
    write_tos_state,
)
from miner_GUI.utils.data import data_dir_gui, log_step

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def check_mysterium_tos_on_startup(window: "MainWindow") -> bool:
    """Check/enforce Mysterium TOS state on GUI startup.

    Returns ``True`` if Mysterium should be initialized (TOS accepted or
    not applicable).  Returns ``False`` if the user declined or TOS is
    not resolved — Mysterium stays disabled.

    Side effects:
      - May write tos_state.json (catch-up flows)
      - Sets ``window._mysterium_enabled`` when daemon is already up
      - Shows catch-up consent dialog for Cohort B
    """
    from config_profile import MINER_CODE

    if MINER_CODE != "BM" or not getattr(window, "_allow_mysterium", False):
        return True

    config_dir = data_dir_gui() / "config"
    tos = read_tos_state(config_dir)

    # --- Already resolved accept ---
    if is_resolved_accept(tos):
        _pre_set_enabled_if_daemon_up(window)
        return True

    # --- Explicitly declined ---
    via = (tos or {}).get("accepted_via", "")
    if via.endswith("-declined"):
        window._mysterium_enabled = False
        log_step("tos_catchup_previously_declined", {"via": via})
        return False

    # --- Pending catch-up or missing tos_state → Cohort check ---
    pending = (tos or {}).get("tos_pending_catchup", False)
    log_step("tos_catchup_needed", {"pending": pending, "tos_present": tos is not None})

    # Cohort A auto-pass: if TequilAPI reports agreed_provider=true,
    # the user already consented through a prior path.  Write marker
    # silently — NO dialog.
    if _check_tequilapi_agreed():
        write_tos_state(config_dir, accepted_via="gui-existing-tequilapi")
        log_step("tos_catchup_cohort_a_autopass", {})
        _pre_set_enabled_if_daemon_up(window)
        return True

    # Cohort B: show consent dialog
    from miner_GUI.ui.helpers.integrations.mysterium import show_mysterium_consent_dialog

    if show_mysterium_consent_dialog(window):
        write_tos_state(config_dir, accepted_via="gui-catchup")
        log_step("tos_catchup_accepted", {})
        window._mysterium_catchup_just_accepted = True
        return True
    else:
        write_tos_state(config_dir, accepted_via="gui-catchup-declined")
        window._mysterium_enabled = False
        log_step("tos_catchup_declined", {})
        return False


def _pre_set_enabled_if_daemon_up(window: "MainWindow") -> None:
    """If TequilAPI healthcheck responds, pre-set _mysterium_enabled = True.

    This is the key mechanism that eliminates the post-install pause:
    when init_mysterium_support() → _on_status_ready() runs, it reads
    _mysterium_enabled=True and shows the panel as enabled without
    dispatching the _MysteriumSetupWorker (no progress dialog).
    """
    try:
        import requests
        resp = requests.get("http://127.0.0.1:4050/healthcheck", timeout=2)
        if resp.status_code == 200:
            window._mysterium_enabled = True
            log_step("tos_catchup_daemon_already_up", {})
    except Exception:
        # Daemon not up — leave _mysterium_enabled as None.
        # init_mysterium_support will handle bootstrap.
        pass


def _check_tequilapi_agreed() -> bool:
    """Return True if TequilAPI /terms reports agreed_provider=true."""
    try:
        import requests
        resp = requests.get("http://127.0.0.1:4050/terms", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return bool(data.get("agreed_provider"))
    except Exception:
        pass
    return False
