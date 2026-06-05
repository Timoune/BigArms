from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

from .models import (
    CompensationValidationFailedError,
    ExecutionRequest,
    ToolManifest,
    ToolVersionMissingError,
)

logger = logging.getLogger("bigarms.tool_registry")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, ToolManifest]] = defaultdict(dict)
        self._active_transactions: Dict[tuple[str, str], int] = defaultdict(int)

    def register_tool(self, manifest: ToolManifest) -> None:
        name = manifest.name
        version = manifest.version

        if manifest.supports_undo or self._is_mutating_tool(manifest):
            if not manifest.undo_tool or not manifest.undo_tool.strip():
                logger.error("Compensation validation failed for %s@%s", name, version)
                raise CompensationValidationFailedError(
                    f"Tool {name}@{version} declares supports_undo but has no undo_tool"
                )

        self._detect_dependency_cycles(manifest)
        self._tools[name][version] = manifest
        logger.info("Registered tool: %s@%s", name, version)

    def _is_mutating_tool(self, manifest: ToolManifest) -> bool:
        for cap in manifest.required_capabilities:
            if cap.tier in ("WRITE", "ELEVATED"):
                return True
        return False

    def _detect_dependency_cycles(self, manifest: ToolManifest) -> None:
        graph: Dict[str, List[str]] = defaultdict(list)
        for name, versions in self._tools.items():
            for m in versions.values():
                graph[name].extend(m.dependencies)
        graph[manifest.name].extend(manifest.dependencies)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        if has_cycle(manifest.name):
            raise ValueError(f"Circular dependency detected involving '{manifest.name}'")

    def validate_execution_request(self, request: ExecutionRequest) -> ToolManifest:
        if not request.tool_version:
            raise ToolVersionMissingError("tool_version is mandatory")

        tool_versions = self._tools.get(request.tool_name)
        if not tool_versions or request.tool_version not in tool_versions:
            raise ValueError(f"Tool '{request.tool_name}@{request.tool_version}' not registered")

        manifest = tool_versions[request.tool_version]
        return manifest

    def get_tool(self, name: str, version: str) -> Optional[ToolManifest]:
        return self._tools.get(name, {}).get(version)

    def list_tools(self) -> List[ToolManifest]:
        result = []
        for versions in self._tools.values():
            result.extend(versions.values())
        return result

    def mark_transaction_started(self, tool_name: str, version: str) -> None:
        self._active_transactions[(tool_name, version)] += 1

    def mark_transaction_ended(self, tool_name: str, version: str) -> None:
        key = (tool_name, version)
        if self._active_transactions[key] > 0:
            self._active_transactions[key] -= 1