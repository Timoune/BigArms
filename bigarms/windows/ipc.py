from __future__ import annotations

import json
import logging
import sys
import threading
from typing import Optional

from ..models import ExecutionRequest, ExecutionResult

from ..orchestrator import ExecutionOrchestrator

logger = logging.getLogger("bigarms.windows.ipc")

if sys.platform == "win32":
    try:
        import win32pipe
        import win32file
    except ImportError:
        win32pipe = None
else:
    win32pipe = None


class BigArmsIPCServer:
    def __init__(self, orchestrator: ExecutionOrchestrator, pipe_name: str = r"\\.\pipe\BigArmsExecution"):
        self.orchestrator = orchestrator
        self.pipe_name = pipe_name
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if sys.platform != "win32" or win32pipe is None:
            logger.error("BigArmsIPCServer requires Windows + pywin32")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True, name="BigArms-IPC-v0.5")
        self._thread.start()
        logger.info("BigArms v0.5 IPC server listening on %s", self.pipe_name)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run_server(self) -> None:
        while self._running:
            try:
                pipe = win32pipe.CreateNamedPipe(
                    self.pipe_name,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                    1, 65536, 65536, 0, None
                )
                win32pipe.ConnectNamedPipe(pipe, None)

                raw = win32file.ReadFile(pipe, 65536)[1]
                request = ExecutionRequest(**json.loads(raw.decode("utf-8")))

                result = self.orchestrator.execute(request)

                response = {
                    "correlation_id": result.correlation_id,
                    "success": result.success,
                    "result_data": result.result_data,
                    "error": result.error,
                    "compensation_triggered": result.compensation_triggered,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "duration_ms": result.duration_ms,
                    "resource_usage": result.resource_usage,
                }

                win32file.WriteFile(pipe, json.dumps(response).encode("utf-8"))
                win32file.FlushFileBuffers(pipe)
                win32pipe.DisconnectNamedPipe(pipe)
                win32file.CloseHandle(pipe)

            except Exception as e:
                logger.exception("IPC error: %s", e)
                try:
                    win32file.CloseHandle(pipe)
                except Exception:
                    pass


def create_ipc_server(orchestrator: ExecutionOrchestrator) -> BigArmsIPCServer:
    return BigArmsIPCServer(orchestrator)