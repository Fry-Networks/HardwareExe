"""Docker progress dialog and container-readiness polling utilities.

Shared by all Docker-based integrations (Presearch, Diiisco, Space Acres)
to show a modal splash while the service pulls / starts a container.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PySide6 import QtCore, QtWidgets

from miner_GUI.utils.ops_queue_client import _processed_dir

if TYPE_CHECKING:
    pass

# Seconds before the progress dialog becomes visible.
# If the Docker operation completes faster than this, the dialog never shows.
_SHOW_DELAY = 2.0


def show_docker_progress(
    parent: QtWidgets.QWidget,
    partner_name: str,
) -> QtWidgets.QProgressDialog:
    """Create a modal progress dialog for a Docker container start.

    The dialog is created **hidden**.  ``poll_docker_operation`` will show
    it after ``_SHOW_DELAY`` seconds — if the container starts quickly
    (images cached), the splash never appears.

    Args:
        parent: Parent widget (usually MainWindow).
        partner_name: Display name ("Diiisco", "Presearch", "Space Acres").

    Returns:
        QProgressDialog — visibility managed by *poll_docker_operation*.
    """
    progress = QtWidgets.QProgressDialog(
        f"Starting {partner_name}...\n"
        "First launch may take several minutes while\n"
        "Docker images are downloaded.",
        "",
        0,
        3,
        parent,
    )
    progress.setWindowTitle(f"FryNetworks - {partner_name}")
    progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
    progress.setCancelButton(None)
    # Prevent Qt from auto-showing — we control visibility ourselves.
    progress.setMinimumDuration(2_000_000_000)
    progress.setValue(0)
    return progress


def poll_container_ready(
    parent: QtWidgets.QWidget,
    is_running_fn: Callable[[], bool],
    progress: QtWidgets.QProgressDialog,
    on_ready: Callable[[], None],
    on_timeout: Callable[[], None],
    partner_name: str,
    max_seconds: int = 900,
    interval_ms: int = 5000,
) -> QtCore.QTimer:
    """Poll until a Docker container is running, keeping the dialog alive.

    Args:
        parent: Parent widget for the QTimer.
        is_running_fn: Returns True when the container is up.
        progress: Progress dialog kept open until resolved.
        on_ready: Called once when the container is detected running.
        on_timeout: Called if *max_seconds* elapses without success.
        partner_name: Display name for the elapsed-time label.
        max_seconds: Maximum wait (default 15 min).
        interval_ms: Poll interval (default 5 s).

    Returns:
        The QTimer (stored by caller so it isn't garbage-collected).
    """
    start_time = time.monotonic()
    timer = QtCore.QTimer(parent)

    def _check() -> None:
        elapsed = time.monotonic() - start_time

        try:
            if is_running_fn():
                timer.stop()
                progress.close()
                on_ready()
                return
        except Exception:
            pass

        if elapsed >= max_seconds:
            timer.stop()
            progress.close()
            on_timeout()
            return

        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        elapsed_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        progress.setLabelText(
            f"Starting {partner_name}...\n"
            f"First launch may take several minutes while\n"
            f"Docker images are downloaded.\n"
            f"Elapsed: {elapsed_str}"
        )

    timer.timeout.connect(_check)
    timer.start(interval_ms)
    return timer


def poll_docker_operation(
    parent: QtWidgets.QWidget,
    request_id: str,
    progress: QtWidgets.QProgressDialog,
    partner_name: str,
    on_ready: Callable[[dict], None],
    on_error: Callable[[str], None],
    on_timeout: Callable[[], None],
    max_seconds: int = 900,
    interval_ms: int = 500,
) -> QtCore.QTimer:
    """Poll service progress/done files for a Docker start operation.

    Reads ``ops_processed/{request_id}.progress.json`` to show real-time
    phase detail (pulling → building → starting) and
    ``ops_processed/{request_id}.done.json`` to detect completion.

    The progress dialog stays hidden for the first ``_SHOW_DELAY`` seconds.
    If ``done.json`` arrives before that, the dialog never appears — the
    in-panel sync bar handles the UX instead.

    Args:
        parent: Parent widget for the QTimer.
        request_id: The ops-queue request ID returned by
            ``enqueue_start_docker_container(..., wait_for_result=False)``.
        progress: Progress dialog (created hidden by *show_docker_progress*).
        partner_name: Display name ("Diiisco", "Presearch", "Space Acres").
        on_ready: Called with the done.json dict when ``success=true``.
        on_error: Called with error message when ``success=false``.
        on_timeout: Called if *max_seconds* elapses without a done file.
        max_seconds: Maximum wait (default 15 min, matches service timeout).
        interval_ms: Poll interval (default 500 ms).

    Returns:
        The QTimer (caller must store it to prevent garbage-collection).
    """
    phase_steps = {"pulling": 1, "building": 2, "starting": 3}

    processed = _processed_dir()
    progress_path = processed / f"{request_id}.progress.json"
    done_path = processed / f"{request_id}.done.json"
    start_time = time.monotonic()
    timer = QtCore.QTimer(parent)
    shown = [False]  # mutable flag — dialog not yet visible

    def _check() -> None:
        elapsed = time.monotonic() - start_time

        # 1. Check for completion
        try:
            if done_path.exists():
                data = json.loads(done_path.read_text(encoding="utf-8"))
                timer.stop()
                if shown[0]:
                    progress.setValue(3)
                    progress.close()
                if data.get("success"):
                    on_ready(data)
                else:
                    on_error(data.get("message", "Docker operation failed."))
                return
        except Exception:
            pass

        # 2. Show dialog after delay (only once)
        if not shown[0] and elapsed >= _SHOW_DELAY:
            progress.show()
            shown[0] = True

        # 3. Timeout
        if elapsed >= max_seconds:
            timer.stop()
            if shown[0]:
                progress.close()
            on_timeout()
            return

        # Skip UI updates while dialog is hidden
        if not shown[0]:
            return

        # 4. Check for phase progress
        phase = ""
        detail = ""
        try:
            if progress_path.exists():
                data = json.loads(progress_path.read_text(encoding="utf-8"))
                phase = data.get("phase", "")
                detail = data.get("detail", "")
        except Exception:
            pass

        # 5. Advance progress bar based on phase
        step = phase_steps.get(phase, 0)
        if step > 0:
            progress.setValue(step)

        # 6. Update dialog text
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        elapsed_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        if detail:
            progress.setLabelText(
                f"Starting {partner_name}...\n"
                f"{detail}\n"
                f"Elapsed: {elapsed_str}"
            )
        else:
            progress.setLabelText(
                f"Starting {partner_name}...\n"
                f"First-time setup may take several minutes.\n"
                f"Elapsed: {elapsed_str}"
            )

    timer.timeout.connect(_check)
    timer.start(interval_ms)
    return timer
