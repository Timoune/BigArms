import pytest
from bigarms.models import (
    CompensationValidationFailedError,
    ExecutionRequest,
    PermissionTier,
    StructuredCapability,
    ToolManifest,
    ToolVersionMissingError,
)
from bigarms.tool_registry import ToolRegistry

@pytest.fixture
def registry():
    return ToolRegistry()

@pytest.fixture
def simple_manifest():
    return ToolManifest(name="file_writer", version="1.2.3")

class TestToolRegistryRegistration:
    def test_register_valid_tool(self, registry, simple_manifest):
        registry.register_tool(simple_manifest)
        assert registry.get_tool("file_writer", "1.2.3") is not None

    def test_register_mutating_tool_without_undo_fails(self, registry):
        bad_manifest = ToolManifest(
            name="dangerous",
            version="1.0",
            supports_undo=True,
            undo_tool="",
        )
        with pytest.raises(CompensationValidationFailedError):
            registry.register_tool(bad_manifest)

class TestDependencyCycleDetection:
    def test_no_cycle_passes(self, registry):
        m1 = ToolManifest(name="A", version="1", dependencies=["B"])
        m2 = ToolManifest(name="B", version="1", dependencies=[])
        registry.register_tool(m2)
        registry.register_tool(m1)

    def test_direct_cycle_raises(self, registry):
        m1 = ToolManifest(name="A", version="1", dependencies=["B"])
        m2 = ToolManifest(name="B", version="1", dependencies=["A"])
        registry.register_tool(m1)
        with pytest.raises(ValueError, match="Circular dependency"):
            registry.register_tool(m2)

class TestExecutionRequestValidation:
    def test_unregistered_tool_raises(self, registry):
        req = ExecutionRequest(
            correlation_id="c1",
            tool_name="unknown",
            tool_version="1.0",
        )
        with pytest.raises(ValueError, match="not registered"):
            registry.validate_execution_request(req)

    def test_valid_registered_tool_passes(self, registry, simple_manifest):
        registry.register_tool(simple_manifest)
        req = ExecutionRequest(
            correlation_id="c1",
            tool_name="file_writer",
            tool_version="1.2.3",
        )
        manifest = registry.validate_execution_request(req)
        assert manifest.version == "1.2.3"