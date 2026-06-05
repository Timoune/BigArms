from __future__ import annotations

import logging
import sys
from typing import List, Set

logger = logging.getLogger("bigarms.windows.wfp")

if sys.platform == "win32":
    try:
        import win32security
    except ImportError:
        win32security = None
else:
    win32security = None


class WFPOutboundFilter:
    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id
        self.filter_ids: List[int] = []
        self._engine_handle = None

    def apply_allowlist(self, allowed_ips: Set[str]) -> None:
        if not allowed_ips:
            logger.debug("[%s] No IP restrictions — skipping WFP allowlist", self.correlation_id)
            return

        if sys.platform != "win32" or win32security is None:
            logger.warning("WFP requires Windows. Allowlist will not be enforced.")
            return

        logger.info(
            "[%s] WFP outbound allowlist applied for IPs: %s (stub - real WFP calls go here)",
            self.correlation_id, allowed_ips
        )

    def remove_filters(self) -> None:
        if not self.filter_ids:
            return
        logger.debug("[%s] Removing %d WFP filters", self.correlation_id, len(self.filter_ids))
        self.filter_ids.clear()

    def close(self) -> None:
        self.remove_filters()


def create_wfp_filter(correlation_id: str, allowed_ips: Set[str]) -> WFPOutboundFilter:
    wfp = WFPOutboundFilter(correlation_id)
    wfp.apply_allowlist(allowed_ips)
    return wfp