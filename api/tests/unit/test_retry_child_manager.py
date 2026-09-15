import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.domain.device_policy import DeviceClassification
from app.operations.manager import (
    AKAMAI_DEVICE_RESET,
    AKAMAI_MFA_DOMAIN,
    EAA_DOMAIN,
    EAA_OTP_RESET,
    OperationManager,
    PrepareOperationError,
)
from app.operations.models import OperationRecord, OperationStatus
from app.operations.repository import OperationStateConflict
from app.services.eaa import EaaCandidate, EaaSearchResult, EaaSearchResultType


NOW = datetime.now(timezone.utc)


def op(
    *,
    operation_id="op_parent",
    operation_type=AKAMAI_DEVICE_RESET,
    domain=AKAMAI_MFA_DOMAIN,
    status=OperationStatus.REQUIRES_RECONFIRMATION,
    destructive_target=None,
    target_identity=None,
):
    return OperationRecord(
        operation_id=operation_id,
        parent_operation_id=None,
        operation_type=operation_type,
        domain=domain,
        actor_context={"actor": "a"},
        session_context={"session": "s"},
        prepared_interaction_ref="parent-prepare",
        target_identity=target_identity or {"user_ref": "usr_safe", "username": "u1"},
        destructive_target=destructive_target or {
            "device_id": "target",
            "postcheck_factor_baseline": [
                {
                    "device_id": "target",
                    "is_target": True,
                    "classification": "USER_AUTHENTICATOR",
                    "reset_eligible": True,
                    "type": "AKAMAI_AUTHENTICATOR",
                    "created_by": "USER",
                    "external_source": None,
                    "platform": "android",
                },
                {
                    "device_id": "protected",
                    "is_target": False,
                    "classification": "EXTERNAL_EAA",
                    "reset_eligible": False,
                    "type": "EMAIL_ADDRESS",
                    "created_by": "EXTERNAL",
                    "external_source": "eaa",
                    "platform": "Email address",
                },
            ],
        },
        prepared_snapshot={},
        status=status,
        prepared_at=NOW,
        confirmed_at=NOW,
        execution_started_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        execution_attempts=1,
        post_check_result={"ambiguous_origin": True},
        outcome_code="target_remains",
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
    )


def factor(
    device_id,
    *,
    reset_eligible,
    classification,
    device_type="AKAMAI_AUTHENTICATOR",
    created_by="USER",
    external_source=None,
    platform="android",
):
    return SimpleNamespace(
        type=device_type,
        created_by=created_by,
        external_source=external_source,
        platform=platform,
        classification=classification,
        reset_eligible=reset_eligible,
        internal=SimpleNamespace(internal_device_id=device_id),
    )


PROTECTED = factor(
    "protected",
    reset_eligible=False,
    classification=DeviceClassification.EXTERNAL_EAA,
    device_type="EMAIL_ADDRESS",
    created_by="EXTERNAL",
    external_source="eaa",
    platform="Email address",
)
TARGET = factor(
    "target",
    reset_eligible=True,
    classification=DeviceClassification.USER_AUTHENTICATOR,
)


class Ops:
    def __init__(self, parent):
        self.parent = parent
        self.created = []
        self.transitions = []

    def get(self, operation_id, **kwargs):
        return self.parent

    def create_retry_child(self, **kwargs):
        self.created.append(kwargs)
        child = op(
            operation_id="op_child",
            operation_type=kwargs["operation_type"],
            domain=kwargs["domain"],
            status=OperationStatus.PREPARED,
            destructive_target=kwargs["destructive_target"],
            target_identity=kwargs["target_identity"],
        )
        return OperationRecord(
            **{
                **child.__dict__,
                "parent_operation_id": kwargs["parent_operation_id"],
                "prepared_interaction_ref": kwargs["prepared_interaction_ref"],
                "execution_attempts": 0,
                "confirmed_at": None,
                "execution_started_at": None,
            }
        )

    def transition(self, operation_id, **kwargs):
        self.transitions.append((operation_id, kwargs))
        return OperationRecord(
            **{
                **self.parent.__dict__,
                "status": kwargs["new_status"],
                "outcome_code": kwargs.get("outcome_code"),
                "post_check_result": kwargs.get("post_check_result"),
            }
        )


class Amfa:
    def __init__(self, factors):
        self.status = SimpleNamespace(
            account_present=True,
            account_status="ACTIVE",
            business_state=None,
            factors=tuple(factors),
        )

    def status_for_username(self, username):
        return self.status


class Eaa:
    def __init__(self):
        safe = SimpleNamespace(
            username="u1",
            display_name="User One",
            eaa_native_mfa_configured=True,
            otp_reset_available=True,
        )
        internal = SimpleNamespace(internal_reset_id="reset-new")
        self.result = EaaSearchResult(
            EaaSearchResultType.FOUND,
            (EaaCandidate(safe=safe, internal=internal),),
        )

    def search(self, username):
        return self.result


def manager(parent, *, factors=(TARGET, PROTECTED), eaa=None):
    ops = Ops(parent)
    mgr = OperationManager(
        operations=ops,
        references=SimpleNamespace(),
        reference_service=SimpleNamespace(),
        eaa_service=eaa or Eaa(),
        akamai_mfa_service=Amfa(factors),
        execution_adapter=SimpleNamespace(enabled=False),
    )
    return mgr, ops


class RetryChildManagerTests(unittest.TestCase):
    def test_parent_must_require_reconfirmation(self):
        parent = op(status=OperationStatus.FAILED)
        mgr, ops = manager(parent)
        with self.assertRaises(OperationStateConflict):
            mgr.prepare_retry(
                parent_operation_id=parent.operation_id,
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="retry-prepare",
                request_id="r1",
            )
        self.assertEqual(ops.created, [])

    def test_akamai_target_present_creates_new_prepared_child(self):
        parent = op()
        mgr, ops = manager(parent)

        result = mgr.prepare_retry(
            parent_operation_id=parent.operation_id,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="retry-prepare",
            request_id="r1",
        )

        self.assertIsNotNone(result.child)
        self.assertFalse(result.already_completed)
        self.assertEqual(result.child.status, OperationStatus.PREPARED)
        self.assertEqual(result.child.parent_operation_id, parent.operation_id)
        self.assertEqual(result.child.prepared_interaction_ref, "retry-prepare")
        self.assertEqual(
            ops.created[0]["destructive_target"]["device_id"],
            "target",
        )
        self.assertEqual(parent.status, OperationStatus.REQUIRES_RECONFIRMATION)

    def test_akamai_target_absent_completes_parent_without_child(self):
        parent = op()
        mgr, ops = manager(parent, factors=(PROTECTED,))

        result = mgr.prepare_retry(
            parent_operation_id=parent.operation_id,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="retry-prepare",
            request_id="r1",
        )

        self.assertTrue(result.already_completed)
        self.assertIsNone(result.child)
        self.assertEqual(result.parent.status, OperationStatus.SUCCEEDED)
        self.assertEqual(ops.created, [])
        self.assertEqual(
            ops.transitions[0][1]["outcome_code"],
            "AKAMAI_MFA_RETRY_TARGET_ALREADY_ABSENT",
        )

    def test_akamai_protected_factor_loss_fails_closed(self):
        parent = op()
        mgr, ops = manager(parent, factors=(TARGET,))

        with self.assertRaises(PrepareOperationError) as ctx:
            mgr.prepare_retry(
                parent_operation_id=parent.operation_id,
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="retry-prepare",
                request_id="r1",
            )

        self.assertEqual(ctx.exception.code, "retry_target_not_safe")
        self.assertEqual(ops.created, [])
        self.assertEqual(
            ops.transitions[0][1]["new_status"],
            OperationStatus.FAILED,
        )

    def test_akamai_target_no_longer_eligible_creates_no_child(self):
        parent = op()
        protected_target = factor(
            "target",
            reset_eligible=False,
            classification=DeviceClassification.UNKNOWN_PROTECTED,
        )
        mgr, ops = manager(parent, factors=(protected_target, PROTECTED))

        with self.assertRaises(PrepareOperationError):
            mgr.prepare_retry(
                parent_operation_id=parent.operation_id,
                actor_context={"actor": "a"},
                session_context={"session": "s"},
                interaction_ref="retry-prepare",
                request_id="r1",
            )

        self.assertEqual(ops.created, [])

    def test_eaa_retry_binds_fresh_internal_target(self):
        parent = op(
            operation_type=EAA_OTP_RESET,
            domain=EAA_DOMAIN,
            destructive_target={"eaa_reset_id": "reset-old"},
        )
        mgr, ops = manager(parent)

        result = mgr.prepare_retry(
            parent_operation_id=parent.operation_id,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            interaction_ref="retry-prepare",
            request_id="r1",
        )

        self.assertEqual(
            ops.created[0]["destructive_target"]["eaa_reset_id"],
            "reset-new",
        )
        self.assertEqual(result.child.parent_operation_id, parent.operation_id)


if __name__ == "__main__":
    unittest.main()
