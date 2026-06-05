import pytest

from bigarms.models import DNSResolutionFailedError, ExecutionRequest, StructuredCapability, ToolManifest

from bigarms.sandbox_manager import SandboxManager

@pytest.fixture
def manager():
    return SandboxManager()

class TestSandboxPreparation:
    def test_prepare_without_hosts(self, manager):
        manifest = ToolManifest(name="local_tool", version="1.0")
        req = ExecutionRequest(correlation_id="c1", tool_name="local_tool", tool_version="1.0")
        ctx = manager.prepare_sandbox(req, manifest)
        assert ctx.pinned_ips == set()

    def test_dns_resolution_failure_raises(self, manager):
        cap = StructuredCapability(tier="READ", allowed_hosts=["this-domain-does-not-exist-12345.com"])
        req = ExecutionRequest(
            correlation_id="bad-dns",
            tool_name="net_tool",
            tool_version="1.0",
            granted_capabilities=[cap],
        )
        manifest = ToolManifest(name="net_tool", version="1.0")
        with pytest.raises(DNSResolutionFailedError):
            manager.prepare_sandbox(req, manifest)

    def test_prepare_with_valid_hosts(self, manager):
        cap = StructuredCapability(tier="READ", allowed_hosts=["example.com"])
        req = ExecutionRequest(
            correlation_id="sandbox-test-1",
            tool_name="net_tool",
            tool_version="1.0",
            granted_capabilities=[cap],
        )
        manifest = ToolManifest(name="net_tool", version="1.0")
        ctx = manager.prepare_sandbox(req, manifest)
        assert len(ctx.pinned_ips) > 0