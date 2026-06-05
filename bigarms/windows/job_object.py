from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("bigarms.windows.job_object")

if sys.platform == "win32":
    try:
        import win32job
        import win32api
        import win32con
    except ImportError:
        win32job = None
else:
    win32job = None


@dataclass
class JobLimits:
    max_cpu_time_ms: Optional[int] = None
    max_working_set_bytes: Optional[int] = None
    max_process_memory_bytes: Optional[int] = None
    max_io_bytes: Optional[int] = None
    max_active_processes: Optional[int] = None
    kill_on_job_close: bool = True
    ui_restrictions: bool = True


class WindowsJobObject:
    def __init__(self, name: Optional[str] = None, limits: Optional[JobLimits] = None):
        self.name = name or f"BigArmsJob_{id(self)}"
        self.limits = limits or JobLimits()
        self._handle: Optional[int] = None
        self._assigned_pids: Set[int] = set()
        self._is_closed = False

        if sys.platform != "win32" or win32job is None:
            return
        self._create_job()

    def _create_job(self) -> None:
        if win32job is None:
            return
        try:
            self._handle = win32job.CreateJobObject(None, self.name)
            self._apply_limits()
        except Exception as e:
            logger.error("Failed to create Job Object '%s': %s", self.name, e)
            raise

    def _apply_limits(self) -> None:
        if not self._handle or win32job is None:
            return
        info = win32job.QueryInformationJobObject(self._handle, win32job.JobObjectExtendedLimitInformation)
        limit_flags = 0
        if self.limits.max_cpu_time_ms is not None:
            info["BasicLimitInformation"]["PerProcessUserTimeLimit"] = self.limits.max_cpu_time_ms * 10000
            limit_flags |= win32job.JOB_OBJECT_LIMIT_PROCESS_TIME
        if self.limits.max_working_set_bytes is not None:
            info["BasicLimitInformation"]["MaximumWorkingSetSize"] = self.limits.max_working_set_bytes
            limit_flags |= win32job.JOB_OBJECT_LIMIT_WORKINGSET
        if self.limits.max_process_memory_bytes is not None:
            info["ProcessMemoryLimit"] = self.limits.max_process_memory_bytes
            limit_flags |= win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        if self.limits.kill_on_job_close:
            limit_flags |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        info["BasicLimitInformation"]["LimitFlags"] = limit_flags
        win32job.SetInformationJobObject(self._handle, win32job.JobObjectExtendedLimitInformation, info)

    def get_resource_stats(self) -> Dict[str, Any]:
        if not self._handle or win32job is None:
            return {}
        try:
            info = win32job.QueryInformationJobObject(self._handle, win32job.JobObjectExtendedLimitInformation)
            basic = info.get("BasicLimitInformation", {})
            return {
                "peak_memory_bytes": info.get("PeakJobMemoryUsed", 0),
                "peak_process_memory_bytes": info.get("PeakProcessMemoryUsed", 0),
                "total_user_time_ms": basic.get("TotalUserTime", 0) // 10000 if basic.get("TotalUserTime") else 0,
                "total_kernel_time_ms": basic.get("TotalKernelTime", 0) // 10000 if basic.get("TotalKernelTime") else 0,
                "active_processes": basic.get("ActiveProcesses", 0),
            }
        except Exception:
            return {}

    def assign_process(self, pid: int) -> None:
        if not self._handle or win32job is None:
            return
        try:
            h_process = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, pid)
            win32job.AssignProcessToJobObject(self._handle, h_process)
            self._assigned_pids.add(pid)
        except Exception as e:
            logger.error("Failed to assign PID to Job: %s", e)

    def close(self) -> None:
        if self._is_closed or not self._handle:
            return
        try:
            if self.limits.kill_on_job_close:
                self.terminate_all()
            win32api.CloseHandle(self._handle)
        finally:
            self._is_closed = True
            self._handle = None

    def terminate_all(self, exit_code: int = 1) -> None:
        if self._handle and win32job:
            try:
                win32job.TerminateJobObject(self._handle, exit_code)
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()