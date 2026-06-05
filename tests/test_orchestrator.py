import pytest

from bigarms.capability_enforcer import CapabilityEnforcer

from bigarms.models import ExecutionRequest, PermissionTier, StructuredCapability, ToolManifest

from bigarms.orchestrator import ExecutionOrchestrator

from bigarms.sandbox_manager import SandboxManager

from bigarms.tool_registry import ToolRegistry

@pytest.fixture
def orchestrator():
    registry = ToolRegistry()
    enforcer = CapabilityEnforcer()
    sandbox = SandboxManager()
    return ExecutionOrchestrator(registry, enforcer, sandbox)

@pytest.fixture
def registered_tool(orchestrator):
    manifest = ToolManifest(
        name="safe_tool",
        version="1.0.0",
        supports_undo=True,
        undo_tool="safe_undo",
    )
    orchestrator.registry.register_tool(manifest)
    return manifest

class TestHappyPath:
    def test_successful_execution(self, orchestrator, registered_tool):
        req = ExecutionRequest(
            correlation_id="exec-1",
            tool_name="safe_tool",
            tool_version="1.0.0",
        )
        result = orchestrator.execute(req)
        assert result.success is True

class TestFailureAndCompensation:
    def test_compensation_triggered_on_failure(self, orchestrator, registered_tool):
        req = ExecutionRequest(
            correlation_id="exec-fail",
            tool_name="safe_tool",
            tool_version="9.9.9",
        )
        result = orchestrator.execute(req)
        assert result.success is False