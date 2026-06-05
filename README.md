# BigArms v0.5 — Windows Execution Kernel for Mini Von

**Complete v0.5 Baseline**

BigArms is the execution and action layer of the Mini Von cognitive AI platform.

## Features (v0.5)

- Real Windows Job Object containment + resource stats
- VHDX differencing disks (filesystem isolation + instant compensation rollback)
- WFP outbound network filtering
- Named Pipe IPC with telemetry
- Structured output parsing
- Improved compensation (calls `manifest.undo_tool`)
- Full test suite

## Structure

```
bigar
ms/
├── __init__.py
├── models.py
├── tool_registry.py
├── capability_enforcer.py
├── sandbox_manager.py
└── orchestrator.py

bigar
ms/windows/
├── __init__.py
├── job_object.py
├── vhdx.py
├── wfp.py
└── ipc.py

tests/
pyproject.toml
LICENSE
README.md
```

## Quick Start

```bash
pip install -e ".[windows]"
pytest tests/ -v
```

Ready for integration with BloodyHeart and the rest of Mini Von.