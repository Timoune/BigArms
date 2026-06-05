from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .capability_enforcer import CapabilityEnforcer

from .models import CompensationSpec, ExecutionRequest, ToolManifest

from .sandbox_manager import SandboxContext, SandboxManager

from .tool_registry import ToolRegistry

from .windows.job_object import WindowsJobObject, create_job_for_execution_request

from .windows.vhdx import VHDXMount, create_isolated_execution_environment

logger = logging.getLogger("bigarms.orchestrator")


@dataclass
class ExecutionResult:
    correlation_id: str
    success: bool
    result_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    compensation_triggered: bool = False
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    resource_usage: Dict[str, Any] = field(default_factory=dict)


class ExecutionOrchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        enforcer: CapabilityEnforcer,
        sandbox_manager: SandboxManager,
    ):
        self.registry = registry
        self.enforcer = enforcer
        self.sandbox_manager = sandbox_manager
        self._audit_log: list[Dict[str, Any]] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        correlation_id = request.correlation_id
        manifest: Optional[ToolManifest] = None
        sandbox_ctx = None
        job: Optional[WindowsJobObject] = None
        vhdx_mount: Optional[VHDXMount] = None

        start_time = time.perf_counter()

        try:
            manifest = self.registry.validate_execution_request(request)
            self.registry.mark_transaction_started(manifest.name, manifest.version)
            self.enforcer.enforce(request, manifest)
            sandbox_ctx = self.sandbox_manager.prepare_sandbox(request, manifest)

            job = create_job_for_execution_request(correlation_id, request.resource_budget)
            vhdx_mount = create_isolated_execution_environment(correlation_id)

            self._write_tamper_evident_log(request, manifest)
            result_data = self._execute_tool_in_sandbox(request, manifest, sandbox_ctx, job, vhdx_mount)

            if job:
                job_stats = job.get_resource_stats()
                if job_stats:
                    result_data.setdefault("resource_usage", {}).update(job_stats)

            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000

            if vhdx_mount and result_data.get("status") in ("completed", "success"):
                from .windows.vhdx import WindowsVHDXManager
                WindowsVHDXManager().commit(vhdx_mount)

            return ExecutionResult(
                correlation_id=correlation_id,
                success=True,
                result_data=result_data,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                resource_usage=result_data.get("resource_usage", {}),
            )

        except Exception as exc:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            compensation_triggered = self._handle_compensation(request, manifest)
            if vhdx_mount:
                from .windows.vhdx import WindowsVHDXManager
                WindowsVHDXManager().discard(vhdx_mount)

            return ExecutionResult(
                correlation_id=correlation_id,
                success=False,
                error=str(exc),
                compensation_triggered=compensation_triggered,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
            )
        finally:
            if manifest:
                self.registry.mark_transaction_ended(manifest.name, manifest.version)
            if sandbox_ctx:
                self.sandbox_manager.teardown_sandbox(correlation_id)
            if job:
                job.close()

    def _write_tamper_evident_log(self, request: ExecutionRequest, manifest: ToolManifest) -> None:
        manifest_hash = hashlib.sha256(str(manifest.model_dump()).encode()).hexdigest()
        binary_hash = hashlib.sha256(f"{manifest.name}:{manifest.version}".encode()).hexdigest()
        self._audit_log.append({
            "correlation_id": request.correlation_id,
            "tool_name": manifest.name,
            "tool_version": manifest.version,
            "manifest_hash": manifest_hash,
            "binary_hash": binary_hash,
        })

    def _execute_tool_in_sandbox(
        self,
        request: ExecutionRequest,
        manifest: ToolManifest,
        sandbox_ctx: SandboxContext,
        job: Optional[WindowsJobObject],
        vhdx_mount: Optional[VHDXMount],
    ) -> Dict[str, Any]:
        correlation_id = request.correlation_id
        tool_id = f"{manifest.name}@{manifest.version}"
        work_dir = str(vhdx_mount.mount_point) if vhdx_mount and vhdx_mount.mount_point else None

        if "command" in request.args:
            command = request.args["command"]
        else:
            command = [sys.executable, "-c", f"print('Executed {tool_id}')"]

        if request.dry_run:
            return {"status": "dry_run", "tool": tool_id, "correlation_id": correlation_id}

        exec_start = time.perf_counter()
        try:
            if sys.platform == "win32" and job is not None:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir, startupinfo=startupinfo)
                job.assign_process(proc.pid)
                stdout, stderr = proc.communicate(timeout=request.resource_budget.get("timeout_seconds", 30))
            else:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir)
                stdout, stderr = proc.communicate(timeout=request.resource_budget.get("timeout_seconds", 30))

            exec_end = time.perf_counter()
            resource_usage = {
                "duration_ms": (exec_end - exec_start) * 1000,
                "exit_code": proc.returncode,
            }

            # v0.5: Try to parse structured JSON output
            structured_output = None
            try:
                stripped = (stdout or "").strip()
                if stripped.startswith("{") or stripped.startswith("["):
                    structured_output = json.loads(stripped)
            except Exception:
                pass

            result = {
                "status": "completed" if proc.returncode == 0 else "failed",
                "tool": tool_id,
                "exit_code": proc.returncode,
                "stdout": stripped,
                "stderr": (stderr or "").strip(),
                "resource_usage": resource_usage,
                "correlation_id": correlation_id,
            }
            if structured_output is not None:
                result["structured_output"] = structured_output

            return result

        except subprocess.TimeoutExpired:
            if "proc" in locals():
                proc.kill()
            if vhdx_mount:
                from .windows.vhdx import WindowsVHDXManager
                WindowsVHDXManager().discard(vhdx_mount)
            return {"status": "timeout", "tool": tool_id, "correlation_id": correlation_id}
        except Exception as e:
            if vhdx_mount:
                from .windows.vhdx import WindowsVHDXManager
                WindowsVHDXManager().discard(vhdx_mount)
            return {"status": "failed", "tool": tool_id, "error": str(e), "correlation_id": correlation_id}

    def _handle_compensation(self, request: ExecutionRequest, manifest: Optional[ToolManifest]) -> bool:
        if not manifest or not getattr(manifest, "undo_tool", None):
            return False

        undo_tool_name = manifest.undo_tool
        logger.warning(
            "[%s] COMPENSATION TRIGGERED: %s@%s → undo_tool='%s'",
            request.correlation_id, manifest.name, manifest.version, undo_tool_name
        )

        try:
            undo_args = dict(request.args)

            compensation_request = ExecutionRequest(
                correlation_id=f"{request.correlation_id}-undo",
                tool_name=undo_tool_name,
                tool_version=manifest.version,
                args=undo_args,
                granted_capabilities=request.granted_capabilities,
                dry_run=request.dry_run,
                safe_mode_level="L1",
                resource_budget=request.resource_budget,
            )

            undo_result = self.execute(compensation_request)

            if undo_result.success:
                logger.info("[%s] Compensation via undo_tool '%s' succeeded", request.correlation_id, undo_tool_name)
            else:
                logger.error("[%s] Compensation via undo_tool '%s' failed: %s", request.correlation_id, undo_tool_name, undo_result.error)

            return True

        except Exception as e:
            logger.exception("[%s] Compensation execution error: %s", request.correlation_id, e)
            return False

    def _write_tamper_evident_log(self, request: ExecutionRequest, manifest: ToolManifest) -> None:
        manifest_hash = hashlib.sha256(str(manifest.model_dump()).encode()).hexdigest()
        binary_hash = hashlib.sha256(f"{manifest.name}:{manifest.version}".encode()).hexdigest()
        self._audit_log.append({
            "correlation_id": request.correlation_id,
            "tool_name": manifest.name,
            "tool_version": manifest.version,
            "manifest_hash": manifest_hash,
            "binary_hash": binary_hash,
        })