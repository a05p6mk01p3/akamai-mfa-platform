import unittest
from types import SimpleNamespace

from app.domain.akamai_mfa import AkamaiMfaFactorRecord
from app.domain.device_policy import classify_device
from app.domain.eaa import EaaUserRecord, SafeEaaUser
from app.operations.execution import DisabledExecutionAdapter
from app.operations.manager import (
    AKAMAI_DEVICE_RESET,
    EAA_OTP_RESET,
    OperationManager,
    PrepareOperationError,
)
from app.services.akamai_mfa import AkamaiMfaStatus, ObservedFactor
from app.services.eaa import EaaCandidate, EaaSearchResult, EaaSearchResultType


class _OpRepo:
    def __init__(self):
        self.calls = []

    def create_prepared(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            operation_id="op_safe",
            operation_type=kwargs["operation_type"],
            domain=kwargs["domain"],
            expires_at="later",
        )


class _ReferenceService:
    def __init__(self, user_target):
        self.user_target = user_target

    def resolve_user_ref(self, user_ref, **kwargs):
        return SimpleNamespace(internal_target=dict(self.user_target))


class _ReferenceRepo:
    def __init__(self, device_target=None, user_ref="usr_safe"):
        self.device_target = device_target
        self.user_ref = user_ref

    def resolve(self, *args, **kwargs):
        return SimpleNamespace(
            internal_target={"device_id": self.device_target},
            target_identity={"user_ref": self.user_ref},
        )


class _EaaService:
    def __init__(self, result):
        self.result = result

    def search(self, username):
        return self.result


class _AkamaiService:
    def __init__(self, status):
        self.status = status

    def status_for_username(self, username):
        return self.status


def eaa_found(reset_id="reset-secret"):
    internal = EaaUserRecord(
        username="u1",
        samaccountname="U1",
        display_name="User One",
        status="1",
        login_mfa=True,
        internal_reset_id=reset_id,
        raw={},
    )
    safe = SafeEaaUser(
        username="u1",
        display_name="User One",
        status="1",
        eaa_native_mfa_configured=True,
        otp_reset_available=bool(reset_id),
    )
    return EaaSearchResult(
        EaaSearchResultType.FOUND,
        (EaaCandidate(safe=safe, internal=internal),),
    )


def factor(device_id, *, created_by="USER", device_type="AKAMAI_AUTHENTICATOR", external_tag=None):
    rec = AkamaiMfaFactorRecord(
        device_type=device_type,
        created_by=created_by,
        external_tag=external_tag,
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


class PrepareManagerTests(unittest.TestCase):
    def manager(self, *, eaa=None, amfa=None, device_target=None, ref_user="usr_safe"):
        ops = _OpRepo()
        manager = OperationManager(
            operations=ops,
            references=_ReferenceRepo(device_target=device_target, user_ref=ref_user),
            reference_service=_ReferenceService({"username": "u1"}),
            eaa_service=_EaaService(eaa or eaa_found()),
            akamai_mfa_service=_AkamaiService(
                amfa or AkamaiMfaStatus(True, "ACTIVE", None, (factor("d1"),), None)
            ),
            execution_adapter=DisabledExecutionAdapter(),
        )
        return manager, ops

    def test_eaa_prepare_binds_internal_reset_target_only_in_repository(self):
        manager, ops = self.manager()
        prepared = manager.prepare_eaa_otp_reset(
            user_ref="usr_safe",
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="turn-1",
            request_id="req",
        )
        self.assertEqual(prepared.operation.operation_type, EAA_OTP_RESET)
        self.assertEqual(ops.calls[0]["destructive_target"], {"eaa_reset_id": "reset-secret"})
        self.assertNotIn("eaa_reset_id", prepared.safe_target)

    def test_akamai_single_eligible_can_bind_without_device_ref(self):
        manager, ops = self.manager()
        prepared = manager.prepare_akamai_mfa_device_reset(
            user_ref="usr_safe",
            device_ref=None,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="turn-1",
            request_id="req",
        )
        self.assertEqual(prepared.operation.operation_type, AKAMAI_DEVICE_RESET)
        self.assertEqual(ops.calls[0]["destructive_target"]["device_id"], "d1")
        self.assertIn("postcheck_factor_baseline", ops.calls[0]["destructive_target"])
        self.assertNotIn("device_id", prepared.safe_target)

    def test_akamai_multiple_eligible_requires_selection(self):
        status = AkamaiMfaStatus(
            True, "ACTIVE", None, (factor("d1"), factor("d2")), None
        )
        manager, ops = self.manager(amfa=status)
        with self.assertRaises(PrepareOperationError) as ctx:
            manager.prepare_akamai_mfa_device_reset(
                user_ref="usr_safe",
                device_ref=None,
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="turn-1",
                request_id="req",
            )
        self.assertEqual(ctx.exception.code, "device_selection_required")
        self.assertEqual(ops.calls, [])

    def test_selected_device_is_revalidated_against_current_eligible_set(self):
        status = AkamaiMfaStatus(
            True, "ACTIVE", None, (factor("d1"), factor("d2")), None
        )
        manager, ops = self.manager(amfa=status, device_target="d2")
        manager.prepare_akamai_mfa_device_reset(
            user_ref="usr_safe",
            device_ref="dev_safe",
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="turn-1",
            request_id="req",
        )
        self.assertEqual(ops.calls[0]["destructive_target"]["device_id"], "d2")
        self.assertIn("postcheck_factor_baseline", ops.calls[0]["destructive_target"])

    def test_stale_device_reference_fails_closed(self):
        manager, ops = self.manager(device_target="missing")
        with self.assertRaises(PrepareOperationError) as ctx:
            manager.prepare_akamai_mfa_device_reset(
                user_ref="usr_safe",
                device_ref="dev_safe",
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="turn-1",
                request_id="req",
            )
        self.assertEqual(ctx.exception.code, "device_reference_stale")
        self.assertEqual(ops.calls, [])

    def test_protected_only_provisioned_returns_business_state_without_operation(self):
        protected = factor(
            "external",
            created_by="EXTERNAL",
            device_type="EMAIL_ADDRESS",
            external_tag="eaa",
        )
        status = AkamaiMfaStatus(
            True,
            "PROVISIONED",
            "already_awaiting_enrollment",
            (protected,),
            None,
        )
        manager, ops = self.manager(amfa=status)
        with self.assertRaises(PrepareOperationError) as ctx:
            manager.prepare_akamai_mfa_device_reset(
                user_ref="usr_safe",
                device_ref=None,
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="turn-1",
                request_id="req",
            )
        self.assertEqual(ctx.exception.code, "already_awaiting_enrollment")
        self.assertEqual(ops.calls, [])


if __name__ == "__main__":
    unittest.main()
