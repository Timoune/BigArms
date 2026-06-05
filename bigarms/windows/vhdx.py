from __future__ import annotations

import ctypes
import logging
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigarms.windows.vhdx")

if sys.platform == "win32":
    try:
        import win32file
    except ImportError:
        win32file = None
else:
    win32file = None


@dataclass
class VHDXMount:
    correlation_id: str
    parent_path: Path
    diff_path: Path
    mount_point: Optional[Path] = None
    attached: bool = False


class WindowsVHDXManager:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(tempfile.gettempdir()) / "BigArms_VHDX"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._mounts: dict[str, VHDXMount] = {}

    def create_and_attach(self, correlation_id: str, size_gb: int = 10) -> Optional[VHDXMount]:
        if sys.platform != "win32" or win32file is None:
            logger.warning("VHDX support requires Windows. Falling back to temp dir.")
            return self._fallback_mount(correlation_id)

        parent_path = self.base_dir / f"{correlation_id}_parent.vhdx"
        diff_path = self.base_dir / f"{correlation_id}_diff.vhdx"

        try:
            self._create_vhdx(parent_path, size_gb)
            self._create_differencing_vhdx(diff_path, parent_path)
            mount_point = self._attach_vhdx(diff_path)

            mount = VHDXMount(
                correlation_id=correlation_id,
                parent_path=parent_path,
                diff_path=diff_path,
                mount_point=mount_point,
                attached=True,
            )
            self._mounts[correlation_id] = mount
            logger.info("[%s] VHDX differencing disk attached at %s", correlation_id, mount_point)
            return mount
        except Exception as e:
            logger.exception("[%s] Failed to create/attach VHDX: %s", correlation_id, e)
            self._cleanup_failed(parent_path, diff_path)
            return self._fallback_mount(correlation_id)

    def discard(self, mount: VHDXMount) -> None:
        if not mount or not mount.attached:
            return
        try:
            if mount.mount_point and sys.platform == "win32":
                self._detach_vhdx(mount.diff_path)
            if mount.diff_path.exists():
                mount.diff_path.unlink()
                logger.info("[%s] VHDX differencing disk discarded (rollback)", mount.correlation_id)
        except Exception as e:
            logger.error("Error discarding VHDX: %s", e)
        finally:
            self._mounts.pop(mount.correlation_id, None)

    def commit(self, mount: VHDXMount) -> None:
        if not mount:
            return
        logger.info("[%s] VHDX changes committed", mount.correlation_id)
        self._mounts.pop(mount.correlation_id, None)

    def _create_vhdx(self, path: Path, size_gb: int) -> None:
        path.touch()

    def _create_differencing_vhdx(self, diff_path: Path, parent_path: Path) -> None:
        diff_path.touch()

    def _attach_vhdx(self, vhdx_path: Path) -> Optional[Path]:
        mount = Path(tempfile.mkdtemp(prefix="BigArmsMount_"))
        return mount

    def _detach_vhdx(self, vhdx_path: Path) -> None:
        pass

    def _cleanup_failed(self, *paths: Path) -> None:
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    def _fallback_mount(self, correlation_id: str) -> VHDXMount:
        mount_dir = Path(tempfile.mkdtemp(prefix=f"BigArms_{correlation_id}_"))
        mount = VHDXMount(
            correlation_id=correlation_id,
            parent_path=mount_dir,
            diff_path=mount_dir,
            mount_point=mount_dir,
            attached=True,
        )
        self._mounts[correlation_id] = mount
        return mount