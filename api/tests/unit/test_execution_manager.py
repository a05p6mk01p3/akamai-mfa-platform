import unittest
from types import SimpleNamespace

from app.domain.akamai_mfa import AkamaiMfaFactorRecord
from app.domain.device_policy import classify_device
from app.domain.eaa import EaaUserRecord, SafeEaaUser
from app.operations.execution import (
    DisabledExecutionAdapter,
    ExecutionBackendDisabled,
    PrimitiveDisposition,
    PrimitiveResult,
    VerificationDisposition,
    VerificationResult,
)
from app.operations.manager import AKAMAI_DEVICE_RESET, EAA_OTP_RESET, OperationManager
from app.operations.models import OperationStatus
from app.services.akamai_mfa import AkamaiMfaStatus, ObservedFactor
from app.services.eaa import EaaCandidate, EaaSearchResult, EaaSearchResultType


def eaa_result(reset_id="reset-secret"):
    internal = EaaUserRecord(
        username="u1",
        samaccountname="U1",
        display_name="User",
        status="1",
        login_mfa=True,
        internal_reset_id=reset_id,
        raw={},
    )
    safe = SafeEaaUser(
        username="u1",
        display_name="User",
        status="1",
        eaa_native_mfa_configured=True,
        otp_reset_available=True,
    )
    return EaaSearchResult(
        EaaSearchResultType.FOUND,
        (EaaCandidate(safe=safe, internal=internal),),
    )


def factor(device_id="d1"):
    rec = AkamaiMfaFactorRecord(
        device_type="AKAMAI_AUTHENTICATOR",
        created_by="USER",
        external_tag=None,
        platform="test",
        internal_device_id=device_id,
        raw={},
    )
    decision = classify_device(rec)
    return ObservedFactor(
        type=rec.device_type,
        created_by=rec.created_by,
        external_source=rec.external_tag,
        platform=rec.platform,
        classification=decision.classification,
        reset_eligible=decision.reset_eligible,
        internal=rec,
    )


def make_op(operation_type=EAA_OTP_RESET, destructive_target=None):
    if destructive_target is None:
        destructive_target = (
            {"eaa_reset_id": "reset-secret"}
            if operation_type == EAA_OTP_RESET
            else {"device_id": "d1"}
        )
    return SimpleNamespace(
        operation_id="op_test",
        operation_type=operation_type,
        domain="test",
        actor_context={"actor": "a"},
        session_context={"session": "s"},
        target_identity={"username": "u1"},
        destructive_target=destructive_target,
        prepared_snapshot={},
        status=OperationStatus.CONFIRMED,
        outcome_code=None,
        post_check_result=None,
    )


class FakeRepo:
    def __init__(self, operation):
        self.operation = operation
        self.transitions = []
        self.claim_calls = 0

    def claim_execution(self, operation_id, **kwargs):
        self.claim_calls += 1
        self.operation = SimpleNamespace(
            **{**self.operation.__dict__, "status": OperationStatus.EXECUTING}
        )
        return self.operation

    def transition(self, operation_id, *, expected_status, new_status, **kwargs):
        if self.operation.status != expected_status:
            raise AssertionError((self.operation.status, expected_status))
        self.transitions.append((expected_status, new_status, kwargs["event_type"]))
        self.operation = SimpleNamespace(
            **{
                **self.operation.__dict__,
                "status": new_status,
                "outcome_code": kwargs.get("outcome_code"),
                "post_check_result": kwargs.get("post_check_result"),
            }
        )
        return self.operation

    def record_verification_observation(self, operation_id, **kwargs):
        if self.operation.status != OperationStatus.VERIFYING:
            raise AssertionError(self.operation.status)
        self.transitions.append(
            (
                OperationStatus.VERIFYING,
                OperationStatus.VERIFYING,
                "VERIFICATION_INCONCLUSIVE",
            )
        )
        self.operation = SimpleNamespace(
            **{
                **self.operation.__dict__,
                "outcome_code": kwargs["outcome_code"],
                "post_check_result": kwargs["post_check_result"],
            }
        )
        return self.operation

    def get(self, operation_id, **kwargs):
        return self.operation


class FakeAdapter:
    enabled = True

    def supports(self, operation):
        return True

    def __init__(self, primitive, verification):
        self.primitive = primitive
        self.verification = verification
        self.mutate_calls = 0
        self.verify_calls = 0

    def mutate(self, operation):
        self.mutate_calls += 1
        return self.primitive

    def verify(self, operation):
        self.verify_calls += 1
        return self.verification


class EaaService:
    def __init__(self, result):
        self.result = result

    def search(self, username):
        return self.result


class AkamaiService:
    def __init__(self, status):
        self.status = status

    def status_for_username(self, username):
        return self.status


class ExecutionManagerTests(unittest.TestCase):
    def manager(self, operation, primitive, verification, *, eaa=None, amfa=None):
        repo = FakeRepo(operation)
        adapter = FakeAdapter(primitive, verification)
        manager = OperationManager(
            operations=repo,
            references=SimpleNamespace(),
            reference_service=SimpleNamespace(),
            eaa_service=EaaService(eaa or eaa_result()),
            akamai_mfa_service=AkamaiService(
                amfa or AkamaiMfaStatus(True, "ACTIVE", None, (factor(),), None)
            ),
            execution_adapter=adapter,
        )
        return manager, repo, adapter

    @staticmethod
    def execute(manager):
        return manager.execute_operation(
            operation_id="op_test",
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            request_id="req",
        )

    def test_disabled_backend_does_not_consume_confirmation(self):
        operation = make_op()
        repo = FakeRepo(operation)
        manager = OperationManager(
            operations=repo,
            references=SimpleNamespace(),
            reference_service=SimpleNamespace(),
            eaa_service=EaaService(eaa_result()),
            akamai_mfa_service=AkamaiService(
                AkamaiMfaStatus(True, "ACTIVE", None, (factor(),), None)
            ),
            execution_adapter=DisabledExecutionAdapter(),
        )
        with self.assertRaises(ExecutionBackendDisabled):
            self.execute(manager)
        self.assertEqual(repo.operation.status, OperationStatus.CONFIRMED)
        self.assertEqual(repo.claim_calls, 0)

    def test_preflight_failure_consumes_confirmation_and_never_mutates(self):
        manager, repo, adapter = self.manager(
            make_op(destructive_target={"eaa_reset_id": "old"}),
            PrimitiveResult(PrimitiveDisposition.EXPECTED, "p", {}),
            VerificationResult(VerificationDisposition.EXPECTED_STATE, "v", {}),
            eaa=eaa_result("current"),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.FAILED)
        self.assertEqual(result.outcome_code, "TARGET_REVALIDATION_FAILED")
        self.assertEqual(adapter.mutate_calls, 0)

    def test_expected_primitive_requires_postcheck_before_success(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.EXPECTED, "primitive-ok", {}),
            VerificationResult(VerificationDisposition.EXPECTED_STATE, "verified", {}),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.SUCCEEDED)
        self.assertIn(
            (OperationStatus.EXECUTING, OperationStatus.VERIFYING, "POST_CHECK_STARTED"),
            repo.transitions,
        )

    def test_ambiguous_then_expected_state_succeeds_without_retry(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.AMBIGUOUS, "ambiguous", {}),
            VerificationResult(VerificationDisposition.EXPECTED_STATE, "absent", {}),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.SUCCEEDED)
        self.assertEqual(adapter.mutate_calls, 1)
        self.assertEqual(adapter.verify_calls, 1)
        self.assertIn(
            (
                OperationStatus.EXECUTING,
                OperationStatus.AMBIGUOUS,
                "PRIMITIVE_OUTCOME_AMBIGUOUS",
            ),
            repo.transitions,
        )

    def test_ambiguous_target_remains_requires_reconfirmation(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.AMBIGUOUS, "ambiguous", {}),
            VerificationResult(VerificationDisposition.TARGET_REMAINS, "remains", {}),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.REQUIRES_RECONFIRMATION)

    def test_ambiguous_inconclusive_stays_verifying(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.AMBIGUOUS, "ambiguous", {}),
            VerificationResult(VerificationDisposition.INCONCLUSIVE, "unknown", {}),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.VERIFYING)
        self.assertTrue(result.post_check_result["ambiguous_origin"])

    def test_later_verify_preserves_ambiguous_origin(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.AMBIGUOUS, "ambiguous", {}),
            VerificationResult(VerificationDisposition.INCONCLUSIVE, "unknown", {}),
        )
        first = self.execute(manager)
        self.assertEqual(first.status, OperationStatus.VERIFYING)

        adapter.verification = VerificationResult(
            VerificationDisposition.TARGET_REMAINS,
            "still-there",
            {},
        )
        second = manager.verify_operation(
            operation_id="op_test",
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            request_id="req-2",
        )
        self.assertEqual(second.status, OperationStatus.REQUIRES_RECONFIRMATION)
        self.assertEqual(adapter.mutate_calls, 1)

    def test_expected_response_but_target_remains_fails(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(PrimitiveDisposition.EXPECTED, "expected", {}),
            VerificationResult(VerificationDisposition.TARGET_REMAINS, "remains", {}),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.FAILED)

    def test_akamai_preflight_matches_only_current_eligible_device(self):
        manager, repo, adapter = self.manager(
            make_op(AKAMAI_DEVICE_RESET, {"device_id": "d1"}),
            PrimitiveResult(PrimitiveDisposition.EXPECTED, "expected", {}),
            VerificationResult(VerificationDisposition.EXPECTED_STATE, "verified", {}),
            amfa=AkamaiMfaStatus(True, "ACTIVE", None, (factor("d1"),), None),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.SUCCEEDED)

    def test_verification_preserves_safe_primitive_metadata(self):
        manager, repo, adapter = self.manager(
            make_op(),
            PrimitiveResult(
                PrimitiveDisposition.EXPECTED,
                "primitive-ok",
                {"upstream_status": 200, "external_mutation_performed": True},
            ),
            VerificationResult(
                VerificationDisposition.INCONCLUSIVE,
                "needs-validation",
                {"success_criterion_validated": False},
            ),
        )
        result = self.execute(manager)
        self.assertEqual(result.status, OperationStatus.VERIFYING)
        self.assertEqual(
            result.post_check_result["primitive"]["upstream_status"],
            200,
        )
        self.assertTrue(
            result.post_check_result["primitive"]["external_mutation_performed"]
        )
        self.assertFalse(
            result.post_check_result["verification"]["success_criterion_validated"]
        )


if __name__ == "__main__":
    unittest.main()
