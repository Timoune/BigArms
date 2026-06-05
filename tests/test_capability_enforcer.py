import json
import threading

import pytest

from bigarms.capability_enforcer import CapabilityEnforcer

from bigarms.models import (
    ApprovalProofExpiredError,
    ApprovalProofReplayDetectedError,
    ExecutionRequest,
    PermissionTier,
    StructuredCapability,
    ToolManifest,
)

@pytest.fixture
def enforcer():
    return CapabilityEnforcer()

@pytest.fixture
def basic_manifest():
    return ToolManifest(name="test_tool", version="1.0")

class TestCapabilityMatching:
    def test_matching_tiers_pass(self, enforcer, basic_manifest):
        req = ExecutionRequest(
            correlation_id="c1",
            tool_name="test_tool",
            tool_version="1.0",
            granted_capabilities=[StructuredCapability(tier=PermissionTier.READ)],
        )
        basic_manifest.required_capabilities = [StructuredCapability(tier=PermissionTier.READ)]
        enforcer.enforce(req, basic_manifest)

    def test_missing_tier_raises(self, enforcer, basic_manifest):
        req = ExecutionRequest(
            correlation_id="c1",
            tool_name="test_tool",
            tool_version="1.0",
            granted_capabilities=[StructuredCapability(tier=PermissionTier.READ)],
        )
        basic_manifest.required_capabilities = [StructuredCapability(tier=PermissionTier.ELEVATED)]
        with pytest.raises(PermissionError):
            enforcer.enforce(req, basic_manifest)

class TestNonceReplayProtection:
    def test_replay_detected(self, enforcer):
        token = json.dumps({
            "issued_at": "2025-01-01T00:00:00+00:00",
            "expires_at": "2030-01-01T00:00:00+00:00",
            "nonce": "replay-nonce-999"
        })
        enforcer._validate_approval_token(token)
        with pytest.raises(ApprovalProofReplayDetectedError):
            enforcer._validate_approval_token(token)

    def test_thread_safety(self, enforcer):
        results = []
        def worker(nonce):
            try:
                token = json.dumps({
                    "issued_at": "2025-01-01T00:00:00+00:00",
                    "expires_at": "2030-01-01T00:00:00+00:00",
                    "nonce": nonce
                })
                enforcer._validate_approval_token(token)
                results.append("ok")
            except Exception as e:
                results.append(str(e))

        threads = [threading.Thread(target=worker, args=(f"nonce-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        assert all(r == "ok" for r in results)