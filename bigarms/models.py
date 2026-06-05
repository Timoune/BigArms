from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

class BigArmsError(Exception):
    code: str = "BIGARMS_ERROR"
    def __init__(self, message: str, code: Optional[str] = None):
        self.code = code or self.code
        super().__init__(message)

class ToolVersionMissingError(BigArmsError):
    code = "TOOL_VERSION_MISSING"

class CompensationValidationFailedError(BigArmsError):
    code = "COMPENSATION_VALIDATION_FAILED"

class DNSResolutionFailedError(BigArmsError):
    code = "DNS_RESOLUTION_FAILED"

class ApprovalProofExpiredError(BigArmsError):
    code = "APPROVAL_PROOF_EXPIRED"

class ApprovalProofReplayDetectedError(BigArmsError):
    code = "APPROVAL_PROOF_REPLAY_DETECTED"

class PermissionTier(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    ELEVATED = "ELEVATED"

class StructuredCapability(BaseModel):
    tier: PermissionTier
    allowed_hosts: Optional[List[str]] = None
    model_config = {"extra": "forbid"}

class ExecutionRequest(BaseModel):
    correlation_id: str
    tool_name: str
    tool_version: str
    args: Dict[str, Any] = {}
    granted_capabilities: List[StructuredCapability] = []
    dry_run: bool = False
    resource_budget: Dict[str, Any] = {}

class ToolManifest(BaseModel):
    name: str
    version: str
    risk_level: str = "medium"
    supports_dry_run: bool = False
    supports_undo: bool = False
    undo_tool: str = ""
    model_config = {"extra": "forbid"}