from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from .models import (
    ApprovalProofExpiredError,
    ApprovalProofReplayDetectedError,
    ExecutionRequest,
    PermissionTier,
    ToolManifest,
)

logger = logging.getLogger("bigarms.capability_enforcer")


@dataclass
class NonceEntry:
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CapabilityEnforcer:
    def __init__(self, public_key: Optional[str] = None):
        self.public_key = public_key
        self._nonce_cache: Dict[str, NonceEntry] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = 60
        self._last_cleanup = time.time()

    def enforce(self, request: ExecutionRequest, tool_manifest: ToolManifest) -> None:
        self._enforce_capability_match(request, tool_manifest)
        self._enforce_elevated_approval(request)
        if request.approval_proof:
            self._validate_approval_token(request.approval_proof)

    def _enforce_capability_match(self, request: ExecutionRequest, tool_manifest: ToolManifest) -> None:
        required_tiers = {cap.tier for cap in tool_manifest.required_capabilities}
        granted_tiers = {cap.tier for cap in request.granted_capabilities}
        missing = required_tiers - granted_tiers
        if missing:
            raise PermissionError(f"Missing required capability tiers: {missing}")

    def _enforce_elevated_approval(self, request: ExecutionRequest) -> None:
        has_elevated = any(cap.tier == PermissionTier.ELEVATED for cap in request.granted_capabilities)
        if has_elevated and not request.approval_proof:
            raise ValueError("approval_proof is mandatory for ELEVATED tier")

    def _validate_approval_token(self, token: str) -> None:
        try:
            payload = json.loads(token)
        except json.JSONDecodeError:
            raise ValueError("Malformed approval_proof token")

        issued_at = self._parse_timestamp(payload.get("issued_at"))
        expires_at = self._parse_timestamp(payload.get("expires_at"))
        nonce = payload.get("nonce")

        if not nonce:
            raise ValueError("approval_proof missing 'nonce'")

        now = datetime.now(timezone.utc)
        if issued_at and now < issued_at:
            raise ApprovalProofExpiredError("Token is not yet valid")
        if expires_at and now > expires_at:
            raise ApprovalProofExpiredError("Approval token has expired")

        self._check_nonce_replay(nonce, expires_at)

    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    def _check_nonce_replay(self, nonce: str, expires_at: Optional[datetime]) -> None:
        with self._lock:
            self._periodic_cleanup()
            if nonce in self._nonce_cache:
                raise ApprovalProofReplayDetectedError(f"Nonce reuse detected: {nonce}")
            expiry = expires_at or datetime.now(timezone.utc)
            self._nonce_cache[nonce] = NonceEntry(expires_at=expiry)

    def _periodic_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        expired = [n for n, entry in self._nonce_cache.items() if entry.expires_at < datetime.now(timezone.utc)]
        for n in expired:
            del self._nonce_cache[n]
        self._last_cleanup = now