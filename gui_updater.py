#!/usr/bin/env python3
"""
GUI Auto-Updater utilities for FRY Miner.

Goals
- Check GitHub releases for a newer version for the current miner type.
- Poll periodically (default 10 minutes; change via env FRY_UPDATE_INTERVAL_SEC or parameter).
- If a newer version is available, download the matching GUI installer/binary asset.
- Provide optional Qt integration hooks to surface status/progress messages to the UI.

This module is dependency-light (uses requests) and optional PySide6 hooks if available.
It does not perform in-place binary swap while the GUI is running; instead it downloads
to a staging folder and exposes callbacks so the GUI can notify the user and/or relaunch
when appropriate.
"""
from __future__ import annotations

import os
import sys
import json
import time
import threading
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests

try:
    from PySide6 import QtCore
    HAVE_QT = True
except Exception:
    HAVE_QT = False


# -------- Version helpers --------

def _parse_ver(s: str) -> list[int]:
    try:
        return [int(x) for x in re.split(r"[^0-9]+", s or "") if x]
    except Exception:
        return [0]


def cmp_ver(a: str, b: str) -> int:
    A, B = _parse_ver(a), _parse_ver(b)
    L = max(len(A), len(B))
    A += [0] * (L - len(A))
    B += [0] * (L - len(B))
    return (A > B) - (A < B)


# -------- Config helpers --------

def _default_repo_for(code: str) -> Tuple[str, str]:
    """Return (owner, repo) for the given miner code, overridable via env.
    Env override: FRY_UPDATE_REPO or FRY_UPDATE_REPO_<CODE> with value like owner/repo
    """
    env_key = f"FRY_UPDATE_REPO_{(code or '').upper()}"
    s = os.environ.get(env_key) or os.environ.get("FRY_UPDATE_REPO")
    if isinstance(s, str) and "/" in s:
        owner, repo = s.split("/", 1)
        return owner.strip(), repo.strip()
    # Fallback generic; replace with your real releases repo
    return ("FryNetworks", "miner-releases")


def _poll_interval_sec(default: int = 600) -> int:
    try:
        v = int(os.environ.get("FRY_UPDATE_INTERVAL_SEC", "0") or 0)
        return v if v >= 60 else default
    except Exception:
        return default


def _download_dir(code: str) -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData")) / "FryNetworks" / f"miner-{code}"
    else:
        base = Path(f"/var/lib/frynetworks/miner-{code}")
    p = base / "updates"
    p.mkdir(parents=True, exist_ok=True)
    return p


# -------- GitHub API helpers --------

def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def latest_release(owner: str, repo: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    r = requests.get(url, headers=_gh_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def release_by_tag(owner: str, repo: str, tag: str) -> dict:
    tag = (tag or "").lstrip("vV")
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    r = requests.get(url, headers=_gh_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def _asset_for(code: str, tag: str, assets: list[dict]) -> Optional[dict]:
    """Choose the asset matching this miner code (Windows EXE)."""
    want_pref = f"FRY_{code.upper()}_v"
    for a in assets or []:
        nm = (a.get("name") or "").strip()
        if nm.upper().startswith(want_pref) and nm.lower().endswith(".exe"):
            return a
    # Fallback: any .exe
    for a in assets or []:
        if str(a.get("name") or "").lower().endswith(".exe"):
            return a
    return None


@dataclass
class UpdateCheckResult:
    has_update: bool
    latest_version: Optional[str]
    asset_name: Optional[str]
    asset_url: Optional[str]
    err: Optional[str] = None


def check_update(code: str, current_version: str, owner: Optional[str] = None, repo: Optional[str] = None) -> UpdateCheckResult:
    try:
        o, r = (owner, repo) if (owner and repo) else _default_repo_for(code)
        rel = latest_release(o, r)
        tag = str(rel.get("tag_name") or rel.get("name") or "").strip().lstrip("vV")
        assets = rel.get("assets") or []
        asset = _asset_for(code, tag, assets)
        if not tag or not asset:
            return UpdateCheckResult(False, None, None, None, err="no_release_or_asset")
        newer = cmp_ver(tag, current_version) > 0
        return UpdateCheckResult(newer, tag, asset.get("name"), asset.get("browser_download_url"))
    except Exception as e:
        return UpdateCheckResult(False, None, None, None, err=str(e))


def _download(url: str, dest: Path, on_progress: Optional[Callable[[int, Optional[int]], None]] = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0) or None
        tmp = dest.with_suffix(dest.suffix + ".part")
        got = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    try:
                        on_progress(got, total)
                    except Exception:
                        pass
        tmp.replace(dest)
    return dest


def download_update(code: str, version: str, url: str, *, on_progress: Optional[Callable[[int, Optional[int]], None]] = None) -> Path:
    fname = url.split("/")[-1].split("?")[0]
    dest = _download_dir(code) / fname
    return _download(url, dest, on_progress)


# -------- Optional Qt integration --------

class GuiAutoUpdater(QtCore.QObject if HAVE_QT else object):
    """Qt-friendly periodic auto-updater.

    Call start() to begin periodic checks. Emits via callbacks:
      - on_status(str)
      - on_progress(downloaded_bytes, total_bytes or None)
      - on_downloaded(path: Path, version: str)
    """
    def __init__(self, code: str, current_version: str, owner: Optional[str] = None, repo: Optional[str] = None,
                 interval_sec: Optional[int] = None,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
                 on_downloaded: Optional[Callable[[Path, str], None]] = None):
        if HAVE_QT:
            super().__init__()
        self.code = code
        self.current_version = current_version
        self.owner = owner
        self.repo = repo
        self.interval_sec = int(interval_sec or _poll_interval_sec())
        self.on_status = on_status
        self.on_progress = on_progress
        self.on_downloaded = on_downloaded
        self._timer = None

    def _emit_status(self, msg: str):
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass

    def _emit_progress(self, got: int, total: Optional[int]):
        if self.on_progress:
            try:
                self.on_progress(got, total)
            except Exception:
                pass

    def _emit_downloaded(self, path: Path, version: str):
        if self.on_downloaded:
            try:
                self.on_downloaded(path, version)
            except Exception:
                pass

    def check_now(self, *, download_if_newer: bool = True):
        """Perform a single check (blocking). Optionally download if newer."""
        res = check_update(self.code, self.current_version, self.owner, self.repo)
        if res.err:
            self._emit_status(f"Update check failed: {res.err}")
            return res
        if res.has_update and res.asset_url:
            self._emit_status(f"Update {res.latest_version} available; downloading...")
            try:
                p = download_update(self.code, res.latest_version or "", res.asset_url, on_progress=self._emit_progress)
                self._emit_status(f"Update downloaded: {p.name}")
                self._emit_downloaded(p, res.latest_version or "")
            except Exception as e:
                self._emit_status(f"Download failed: {e}")
        else:
            self._emit_status("Up to date")
        return res

    def start(self):
        if not HAVE_QT:
            # Fallback: start a simple thread-based poller
            def _loop():
                while True:
                    try:
                        self.check_now(download_if_newer=True)
                    except Exception:
                        pass
                    time.sleep(max(60, self.interval_sec))
            t = threading.Thread(target=_loop, daemon=True)
            t.start()
            return
        # Qt timer-based polling
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(60, self.interval_sec) * 1000)
        self._timer.timeout.connect(lambda: self.check_now(download_if_newer=True))
        # Fire initial check shortly after start
        QtCore.QTimer.singleShot(1500, lambda: self.check_now(download_if_newer=True))
        self._timer.start()


__all__ = [
    "cmp_ver",
    "check_update",
    "download_update",
    "release_by_tag",
    "GuiAutoUpdater",
]
