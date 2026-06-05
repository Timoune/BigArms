import pytest
from pydantic import ValidationError
from bigarms.models import (
    ApprovalProofExpiredError,
    BigArmsError,
    CompensationSpec,
    ExecutionRequest,
    PermissionTier,
    StructuredCapability,
    ToolManifest,
    ToolVersionMissingError,
)

class TestPermissionTier:
    def test_enum_values(self):
        assert PermissionTier.READ.value == "READ"
        assert PermissionTier.ELEVATED.value == "ELEVATED"
        assert len(PermissionTier) == 4

class TestStructuredCapability:
    def test_valid_capability(self):
        cap = StructuredCapability(tier=PermissionTier.WRITE, allowed_paths=["/tmp/*"])
        assert cap.tier == PermissionTier.WRITE

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            StructuredCapability(tier=PermissionTier.READ, unknown_field=True)

class TestExecutionRequest:
    def test_valid_request(self):
        req = ExecutionRequest(
            correlation_id="corr-1",
            tool_name="test_tool",
            tool_version="1.0.0",
        )
        assert req.tool_version == "1.0.0"

    def test_tool_version_is_mandatory(self):
        with pytest.raises(ToolVersionMissingError):
            ExecutionRequest(
                correlation_id="corr-1",
                tool_name="test_tool",
                tool_version="",
            )

    def test_elevated_requires_approval_proof(self):
        cap = StructuredCapability(tier=PermissionTier.ELEVATED)
        with pytest.raises(ValueError, match="approval_proof is required"):
            ExecutionRequest(
                correlation_id="corr-1",
                tool_name="elevated_tool",
                tool_version="1.0.0",
                granted_capabilities=[cap],
            )

    def test_elevated_with_approval_proof_passes(self):
        cap = StructuredCapability(tier=PermissionTier.ELEVATED)
        req = ExecutionRequest(
            correlation_id="corr-1",
            tool_name="elevated_tool",
            tool_version="1.0.0",
            granted_capabilities=[cap],
            approval_proof='{"nonce": "abc123"}',
        )
        assert req.approval_proof is not None

class TestCompensationSpec:
    def test_valid_compensation(self):
        spec = CompensationSpec(
            undo_tool="undo_file_write",
            idempotency_key="undo-123",
        )
        assert spec.is_idempotent is True

class TestToolManifest:
    def test_valid_manifest(self):
        manifest = ToolManifest(name="test", version="1.0")
        assert manifest.dependencies == []