from __future__ import annotations

def load_live_panel(group: str, width: int = 800, screen_size: str = "desktop"):
    """Return a QWidget implementing a live panel for the given miner group.
    Known groups: 'BM' -> bandwidth panel, 'SVN' -> Storage Validator Nodes,
    'RDN' -> Compute Nodes, 'SDN' -> Storage Decentralization Nodes.
    Returns None if no panel is available.
    """
    try:
        grp = (group or "").strip()
        if grp in ("BM", "Bandwidth"):  # keep Bandwidth as legacy alias
            from .bandwidth import BandwidthPanel
            return BandwidthPanel(width=width, screen_size=screen_size)
        if grp == "AEM":
            from .aem import AemPanel
            return AemPanel(width=width)
        if grp == "Decibel":
            from .decibel import DecibelPanel
            return DecibelPanel(width=width)
        if grp == "Satellite":
            from .satellite import SatellitePanel
            return SatellitePanel(width=width)
        if grp == "Radiation":
            from .geiger import GeigerPanel
            return GeigerPanel(width=width)
        if grp == "SVN":
            from .svn import SvnPanel
            return SvnPanel(width=width, screen_size=screen_size)
        if grp == "RDN":
            from .rdn import RdnPanel
            return RdnPanel(width=width, screen_size=screen_size)
        if grp == "SDN":
            from .sdn import SdnPanel
            return SdnPanel(width=width, screen_size=screen_size)
    except Exception:
        return None
    return None
