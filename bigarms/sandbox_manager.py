from __future__ import annotations

import logging
import socket
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .models import DNSResolutionFailedError, ExecutionRequest, StructuredCapability, ToolManifest

from .windows.job_object import WindowsJobObject, create_job_for_execution_request

from .windows.wfp import WFPOutboundFilter, create_wfp_filter

logger = logging.getLogger("bigarms.sandbox_manager")


@dataclass
class SandboxContext:
    correlation_id: str
    tool_name: str
    tool_version: str
    pinned_ips: Set[str] = field(default_factory=set)
    dns_resolution_policy: str = "pin_at_start"
    job: Optional[WindowsJobObject] = None
    wfp_filter: Optional[WFPOutboundFilter] = None


class SandboxManager:
    def __init__(self):
        self._active_sandboxes: Dict[str, SandboxContext] = {}

    def prepare_sandbox(self, request: ExecutionRequest, tool_manifest: ToolManifest) -> SandboxContext:
        correlation_id = request.correlation_id
        allowed_hosts = self._extract_allowed_hosts(request.granted_capabilities)
        policy = getattr(tool_manifest, "dns_resolution_policy", "pin_at_start")

        pinned_ips: Set[str] = set()
        if allowed_hosts and policy == "pin_at_start":
            pinned_ips = self._resolve_and_pin_hosts(allowed_hosts, correlation_id)

        job = create_job_for_execution_request(correlation_id, request.resource_budget)

        wfp_filter = None
        if pinned_ips:
            wfp_filter = create_wfp_filter(correlation_id, pinned_ips)

        ctx = SandboxContext(
            correlation_id=correlation_id,
            tool_name=tool_manifest.name,
            tool_version=tool_manifest.version,
            pinned_ips=pinned_ips,
            dns_resolution_policy=policy,
            job=job,
            wfp_filter=wfp_filter,
        )
        self._active_sandboxes[correlation_id] = ctx
        return ctx

    def teardown_sandbox(self, correlation_id: str) -> None:
        ctx = self._active_sandboxes.pop(correlation_id, None)
        if ctx:
            if ctx.wfp_filter:
                ctx.wfp_filter.remove_filters()
            if ctx.job:
                ctx.job.close()

    def _extract_allowed_hosts(self, capabilities: List[StructuredCapability]) -> List[str]:
        hosts: Set[str] = set()
        for cap in capabilities:
            if cap.allowed_hosts:
                hosts.update(cap.allowed_hosts)
        return list(hosts)

    def _resolve_and_pin_hosts(self, hosts: List[str], correlation_id: str) -> Set[str]:
        pinned: Set[str] = set()
        for host in hosts:
            try:
                addr_info = socket.getaddrinfo(host, None)
                ips = {info[4][0] for info in addr_info}
                pinned.update(ips)
            except socket.gaierror as e:
                raise DNSResolutionFailedError(f"Failed to resolve {host}") from e
        if not pinned and hosts:
            raise DNSResolutionFailedError("All DNS resolutions failed")
        return pinned