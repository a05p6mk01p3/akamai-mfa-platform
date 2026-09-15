from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..references.models import ReferenceType
from ..references.repository import SafeReferenceError, SafeReferenceRepository
from ..references.service import SafeReferenceService
from ..services.akamai_mfa import AkamaiMfaService, ObservedFactor
from ..services.eaa import EaaSearchResultType, EaaService
from .execution import (
    ExecutionAdapter,
    ExecutionBackendDisabled,
    PrimitiveDisposition,
    VerificationDisposition,
)
from .models import OperationRecord, OperationStatus
from .repository import OperationRepository, OperationStateConflict


EAA_OTP_RESET = "EAA_NATIVE_MFA_OTP_RESET"
AKAMAI_DEVICE_RESET = "AKAMAI_MFA_DEVICE_RESET"

EAA_DOMAIN = "eaa_native_mfa"
AKAMAI_MFA_DOMAIN = "akamai_mfa"


class PrepareOperationError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PreparedOperation:
    operation: OperationRecord
    safe_target: Mapping[str, Any]


@dataclass(frozen=True)
class RetryPreparation:
    parent: OperationRecord
    child: OperationRecord | None
    safe_target: Mapping[str, Any]
    already_completed: bool = False


class OperationManager:
    """Prepare-only orchestration for change-set 04.

    No destructive upstream primitive is present or invoked here.
    """

    def __init__(
        self,
        *,
        operations: OperationRepository,
        references: SafeReferenceRepository,
        reference_service: SafeReferenceService,
        eaa_service: EaaService,
        akamai_mfa_service: AkamaiMfaService,
        execution_adapter: ExecutionAdapter,
    ) -> None:
        self.operations = operations
        self.references = references
        self.reference_service = reference_service
        self.eaa_service = eaa_service
        self.akamai_mfa_service = akamai_mfa_service
        self.execution_adapter = execution_adapter

    def _resolve_user_ref(
        self,
        user_ref: str,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
    ):
        try:
            return self.reference_service.resolve_user_ref(
                user_ref,
                actor_context=actor_context,
                session_context=session_context,
            )
        except SafeReferenceError:
            raise

    def prepare_eaa_otp_reset(
        self,
        *,
        user_ref: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> PreparedOperation:
        identity_ref = self._resolve_user_ref(
            user_ref,
            actor_context=actor_context,
            session_context=session_context,
        )
        username = identity_ref.internal_target.get("username")
        if not isinstance(username, str) or not username.strip():
            raise PrepareOperationError(
                "target_revalidation_failed",
                "A referência de usuário não possui identidade revalidável.",
            )

        current = self.eaa_service.search(username)
        if current.result != EaaSearchResultType.FOUND or len(current.candidates) != 1:
            raise PrepareOperationError(
                "target_revalidation_failed",
                "A identidade EAA não pôde ser revalidada de forma inequívoca.",
            )

        candidate = current.candidates[0]
        reset_id = candidate.internal.internal_reset_id
        if not reset_id:
            raise PrepareOperationError(
                "otp_reset_unavailable",
                "O usuário não possui identificador interno disponível para reset de OTP.",
            )

        target_identity = {
            "user_ref": user_ref,
            "username": candidate.safe.username,
            "display_name": candidate.safe.display_name,
        }
        prepared_snapshot = {
            "username": candidate.safe.username,
            "display_name": candidate.safe.display_name,
            "eaa_native_mfa_configured": candidate.safe.eaa_native_mfa_configured,
            "otp_reset_available": candidate.safe.otp_reset_available,
        }

        op = self.operations.create_prepared(
            operation_type=EAA_OTP_RESET,
            domain=EAA_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            prepared_interaction_ref=interaction_ref,
            target_identity=target_identity,
            destructive_target={"eaa_reset_id": reset_id},
            prepared_snapshot=prepared_snapshot,
            request_id=request_id,
        )
        return PreparedOperation(operation=op, safe_target=target_identity)

    def confirm_operation(
        self,
        *,
        operation_id: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> OperationRecord:
        """Accept later-human-interaction attestation and confirm only.

        The API state transition is owned by the repository. This method does not
        claim execution and cannot call any upstream destructive primitive.
        """
        return self.operations.confirm(
            operation_id,
            actor_context=actor_context,
            session_context=session_context,
            confirmation_interaction_ref=interaction_ref,
            request_id=request_id,
        )

    def _preflight(self, operation: OperationRecord) -> tuple[bool, dict[str, Any]]:
        """Read-only target revalidation immediately before the primitive adapter."""
        target = dict(operation.destructive_target or {})
        username = operation.target_identity.get("username")

        if operation.operation_type == EAA_OTP_RESET:
            if not isinstance(username, str) or not username:
                return False, {"reason": "username_missing"}
            expected_reset_id = target.get("eaa_reset_id")
            if not isinstance(expected_reset_id, str) or not expected_reset_id:
                return False, {"reason": "eaa_target_missing"}
            current = self.eaa_service.search(username)
            if current.result != EaaSearchResultType.FOUND or len(current.candidates) != 1:
                return False, {"reason": "eaa_identity_not_exact"}
            candidate = current.candidates[0]
            if candidate.internal.internal_reset_id != expected_reset_id:
                return False, {"reason": "eaa_target_changed"}
            if not candidate.safe.otp_reset_available:
                return False, {"reason": "otp_reset_not_available"}
            return True, {
                "preflight": "passed",
                "operation_type": EAA_OTP_RESET,
                "target_revalidated": True,
            }

        if operation.operation_type == AKAMAI_DEVICE_RESET:
            if not isinstance(username, str) or not username:
                return False, {"reason": "username_missing"}
            expected_device_id = target.get("device_id")
            if not isinstance(expected_device_id, str) or not expected_device_id:
                return False, {"reason": "device_target_missing"}
            status = self.akamai_mfa_service.status_for_username(username)
            if not status.account_present:
                return False, {"reason": "akamai_mfa_account_absent"}
            matches = [
                factor
                for factor in status.factors
                if factor.reset_eligible
                and factor.internal.internal_device_id == expected_device_id
            ]
            if len(matches) != 1:
                return False, {"reason": "device_target_not_currently_eligible"}
            return True, {
                "preflight": "passed",
                "operation_type": AKAMAI_DEVICE_RESET,
                "target_revalidated": True,
            }

        return False, {"reason": "unsupported_operation_type"}

    def _apply_verification(
        self,
        operation: OperationRecord,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        request_id: str | None,
        ambiguous_origin: bool,
    ) -> OperationRecord:
        verification = self.execution_adapter.verify(operation)
        prior = dict(operation.post_check_result or {})
        observation = {
            **prior,
            "verification": {
                "code": verification.safe_code,
                "disposition": verification.disposition.value,
                **dict(verification.safe_details),
            },
            "code": verification.safe_code,
            "disposition": verification.disposition.value,
            "ambiguous_origin": ambiguous_origin,
        }

        if verification.disposition == VerificationDisposition.EXPECTED_STATE:
            return self.operations.transition(
                operation.operation_id,
                expected_status=OperationStatus.VERIFYING,
                new_status=OperationStatus.SUCCEEDED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="POST_CHECK_CONFIRMED",
                request_id=request_id,
                outcome_code=verification.safe_code,
                post_check_result=observation,
            )

        if verification.disposition == VerificationDisposition.TARGET_REMAINS:
            if ambiguous_origin:
                return self.operations.transition(
                    operation.operation_id,
                    expected_status=OperationStatus.VERIFYING,
                    new_status=OperationStatus.REQUIRES_RECONFIRMATION,
                    actor_context=actor_context,
                    session_context=session_context,
                    event_type="TARGET_REMAINS_RECONFIRMATION_REQUIRED",
                    request_id=request_id,
                    outcome_code=verification.safe_code,
                    post_check_result=observation,
                )
            return self.operations.transition(
                operation.operation_id,
                expected_status=OperationStatus.VERIFYING,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="POST_CHECK_FAILED",
                request_id=request_id,
                outcome_code=verification.safe_code,
                post_check_result=observation,
            )

        if verification.disposition == VerificationDisposition.WRONG_STATE:
            return self.operations.transition(
                operation.operation_id,
                expected_status=OperationStatus.VERIFYING,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="POST_CHECK_FAILED",
                request_id=request_id,
                outcome_code=verification.safe_code,
                post_check_result=observation,
            )

        return self.operations.record_verification_observation(
            operation.operation_id,
            actor_context=actor_context,
            session_context=session_context,
            post_check_result=observation,
            outcome_code=verification.safe_code,
            request_id=request_id,
        )

    def execute_operation(
        self,
        *,
        operation_id: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        request_id: str | None,
    ) -> OperationRecord:
        """Consume confirmation and run the configured internal state-machine adapter."""
        if not getattr(self.execution_adapter, "enabled", False):
            # Environment/configuration failure must not consume confirmation.
            raise ExecutionBackendDisabled("execution backend disabled")

        candidate = self.operations.get(
            operation_id,
            actor_context=actor_context,
            session_context=session_context,
        )
        if not self.execution_adapter.supports(candidate):
            raise ExecutionBackendDisabled(
                "execution backend does not support this operation type"
            )

        claimed = self.operations.claim_execution(
            operation_id,
            actor_context=actor_context,
            session_context=session_context,
            request_id=request_id,
        )

        ok, preflight = self._preflight(claimed)
        if not ok:
            return self.operations.transition(
                operation_id,
                expected_status=OperationStatus.EXECUTING,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="TARGET_REVALIDATION_FAILED",
                request_id=request_id,
                outcome_code="TARGET_REVALIDATION_FAILED",
                post_check_result={
                    **preflight,
                    "external_mutation_performed": False,
                },
            )

        primitive = self.execution_adapter.mutate(claimed)
        primitive_meta = {
            "code": primitive.safe_code,
            "disposition": primitive.disposition.value,
            **dict(primitive.safe_details),
        }

        if primitive.disposition == PrimitiveDisposition.FAILED:
            return self.operations.transition(
                operation_id,
                expected_status=OperationStatus.EXECUTING,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="PRIMITIVE_FAILED",
                request_id=request_id,
                outcome_code=primitive.safe_code,
                post_check_result={
                    "preflight": preflight,
                    "primitive": primitive_meta,
                },
            )

        if primitive.disposition == PrimitiveDisposition.AMBIGUOUS:
            self.operations.transition(
                operation_id,
                expected_status=OperationStatus.EXECUTING,
                new_status=OperationStatus.AMBIGUOUS,
                actor_context=actor_context,
                session_context=session_context,
                event_type="PRIMITIVE_OUTCOME_AMBIGUOUS",
                request_id=request_id,
                outcome_code=primitive.safe_code,
                post_check_result={
                    "preflight": preflight,
                    "primitive": primitive_meta,
                },
            )
            verifying = self.operations.transition(
                operation_id,
                expected_status=OperationStatus.AMBIGUOUS,
                new_status=OperationStatus.VERIFYING,
                actor_context=actor_context,
                session_context=session_context,
                event_type="VERIFICATION_STARTED",
                request_id=request_id,
                outcome_code=primitive.safe_code,
                post_check_result={
                    "preflight": preflight,
                    "primitive": primitive_meta,
                    "ambiguous_origin": True,
                },
            )
            return self._apply_verification(
                verifying,
                actor_context=actor_context,
                session_context=session_context,
                request_id=request_id,
                ambiguous_origin=True,
            )

        verifying = self.operations.transition(
            operation_id,
            expected_status=OperationStatus.EXECUTING,
            new_status=OperationStatus.VERIFYING,
            actor_context=actor_context,
            session_context=session_context,
            event_type="POST_CHECK_STARTED",
            request_id=request_id,
            outcome_code=primitive.safe_code,
            post_check_result={
                "preflight": preflight,
                "primitive": primitive_meta,
                "ambiguous_origin": False,
            },
        )
        return self._apply_verification(
            verifying,
            actor_context=actor_context,
            session_context=session_context,
            request_id=request_id,
            ambiguous_origin=False,
        )

    def verify_operation(
        self,
        *,
        operation_id: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        request_id: str | None,
    ) -> OperationRecord:
        """Observation-only continuation. Never calls mutate()."""
        if not getattr(self.execution_adapter, "enabled", False):
            raise ExecutionBackendDisabled("execution backend disabled")

        operation = self.operations.get(
            operation_id,
            actor_context=actor_context,
            session_context=session_context,
        )
        if operation.status != OperationStatus.VERIFYING:
            from .repository import OperationStateConflict
            raise OperationStateConflict(
                f"verify requires VERIFYING, found {operation.status.value}"
            )

        snapshot = dict(operation.post_check_result or {})
        primitive = snapshot.get("primitive")
        ambiguous_origin = bool(snapshot.get("ambiguous_origin"))
        if isinstance(primitive, Mapping) and primitive.get("disposition") == "ambiguous":
            ambiguous_origin = True

        return self._apply_verification(
            operation,
            actor_context=actor_context,
            session_context=session_context,
            request_id=request_id,
            ambiguous_origin=ambiguous_origin,
        )

    @staticmethod
    def _akamai_retry_baseline(
        status,
        *,
        target_device_id: str,
    ) -> list[dict[str, Any]]:
        baseline: list[dict[str, Any]] = []
        for factor in status.factors:
            current_id = factor.internal.internal_device_id
            baseline.append(
                {
                    "device_id": current_id,
                    "is_target": current_id == target_device_id if current_id else False,
                    "classification": factor.classification.value,
                    "reset_eligible": factor.reset_eligible,
                    "type": factor.type,
                    "created_by": factor.created_by,
                    "external_source": factor.external_source,
                    "platform": factor.platform,
                }
            )
        return baseline

    @staticmethod
    def _baseline_non_target_preserved(
        baseline: list[dict[str, Any]],
        status,
    ) -> tuple[bool, bool]:
        """Return (all non-target preserved, all protected preserved)."""
        current_ids = {
            factor.internal.internal_device_id
            for factor in status.factors
            if factor.internal.internal_device_id
        }

        non_target_preserved = True
        protected_preserved = True

        for item in baseline:
            if not isinstance(item, dict) or item.get("is_target"):
                continue
            device_id = item.get("device_id")
            if isinstance(device_id, str) and device_id:
                present = device_id in current_ids
                if not present:
                    non_target_preserved = False
                    if not bool(item.get("reset_eligible")):
                        protected_preserved = False

        return non_target_preserved, protected_preserved

    def _prepare_eaa_retry(
        self,
        parent: OperationRecord,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> RetryPreparation:
        username = parent.target_identity.get("username")
        if not isinstance(username, str) or not username:
            raise PrepareOperationError(
                "retry_target_not_safe",
                "A identidade EAA da operação anterior não pode ser revalidada.",
            )

        current = self.eaa_service.search(username)
        if current.result != EaaSearchResultType.FOUND or len(current.candidates) != 1:
            raise PrepareOperationError(
                "retry_target_not_safe",
                "A identidade EAA não pôde ser revalidada de forma inequívoca.",
            )

        candidate = current.candidates[0]
        reset_id = candidate.internal.internal_reset_id
        if not reset_id or not candidate.safe.otp_reset_available:
            raise PrepareOperationError(
                "retry_target_not_safe",
                "O reset de OTP EAA não está disponível no estado atual.",
            )

        target_identity = {
            "user_ref": parent.target_identity.get("user_ref"),
            "username": candidate.safe.username,
            "display_name": candidate.safe.display_name,
        }
        prepared_snapshot = {
            "username": candidate.safe.username,
            "display_name": candidate.safe.display_name,
            "eaa_native_mfa_configured": candidate.safe.eaa_native_mfa_configured,
            "otp_reset_available": candidate.safe.otp_reset_available,
            "retry_child": True,
        }

        child = self.operations.create_retry_child(
            parent_operation_id=parent.operation_id,
            operation_type=EAA_OTP_RESET,
            domain=EAA_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            prepared_interaction_ref=interaction_ref,
            target_identity=target_identity,
            destructive_target={"eaa_reset_id": reset_id},
            prepared_snapshot=prepared_snapshot,
            request_id=request_id,
        )
        return RetryPreparation(
            parent=parent,
            child=child,
            safe_target=target_identity,
        )

    def _prepare_akamai_retry(
        self,
        parent: OperationRecord,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> RetryPreparation:
        username = parent.target_identity.get("username")
        target = dict(parent.destructive_target or {})
        target_device_id = target.get("device_id")
        old_baseline = target.get("postcheck_factor_baseline")

        if (
            not isinstance(username, str)
            or not username
            or not isinstance(target_device_id, str)
            or not target_device_id
            or not isinstance(old_baseline, list)
        ):
            raise PrepareOperationError(
                "retry_target_not_safe",
                "A operação anterior não possui target revalidável para retry.",
            )

        status = self.akamai_mfa_service.status_for_username(username)

        if not status.account_present:
            self.operations.transition(
                parent.operation_id,
                expected_status=OperationStatus.REQUIRES_RECONFIRMATION,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="RETRY_PREPARE_UNSAFE_STATE",
                request_id=request_id,
                outcome_code="AKAMAI_MFA_RETRY_ACCOUNT_ABSENT",
                post_check_result={
                    **dict(parent.post_check_result or {}),
                    "retry_prepare_observation": {
                        "account_present": False,
                        "target_absent": True,
                    },
                },
            )
            raise PrepareOperationError(
                "retry_target_not_safe",
                "A conta Akamai MFA não está presente; nenhum retry foi preparado.",
            )

        non_target_preserved, protected_preserved = (
            self._baseline_non_target_preserved(old_baseline, status)
        )

        if not non_target_preserved or not protected_preserved:
            self.operations.transition(
                parent.operation_id,
                expected_status=OperationStatus.REQUIRES_RECONFIRMATION,
                new_status=OperationStatus.FAILED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="RETRY_PREPARE_UNSAFE_STATE",
                request_id=request_id,
                outcome_code="AKAMAI_MFA_RETRY_FACTOR_LOSS",
                post_check_result={
                    **dict(parent.post_check_result or {}),
                    "retry_prepare_observation": {
                        "account_present": True,
                        "non_target_factors_preserved": non_target_preserved,
                        "protected_factors_preserved": protected_preserved,
                    },
                },
            )
            raise PrepareOperationError(
                "retry_target_not_safe",
                "O estado atual perdeu fatores que deveriam ser preservados; nenhum retry foi preparado.",
            )

        current_target_matches = [
            factor
            for factor in status.factors
            if factor.internal.internal_device_id == target_device_id
        ]

        if not current_target_matches:
            updated_parent = self.operations.transition(
                parent.operation_id,
                expected_status=OperationStatus.REQUIRES_RECONFIRMATION,
                new_status=OperationStatus.SUCCEEDED,
                actor_context=actor_context,
                session_context=session_context,
                event_type="RETRY_PREPARE_EFFECT_ALREADY_PRESENT",
                request_id=request_id,
                outcome_code="AKAMAI_MFA_RETRY_TARGET_ALREADY_ABSENT",
                post_check_result={
                    **dict(parent.post_check_result or {}),
                    "retry_prepare_observation": {
                        "account_present": True,
                        "account_status": status.account_status,
                        "target_absent": True,
                        "non_target_factors_preserved": True,
                        "protected_factors_preserved": True,
                        "child_created": False,
                    },
                },
            )
            return RetryPreparation(
                parent=updated_parent,
                child=None,
                safe_target=dict(parent.target_identity),
                already_completed=True,
            )

        eligible_target_matches = [
            factor
            for factor in current_target_matches
            if factor.reset_eligible
        ]
        if len(eligible_target_matches) != 1:
            raise PrepareOperationError(
                "retry_target_not_safe",
                "O target anterior ainda existe, mas não está mais elegível para reset.",
            )

        selected = eligible_target_matches[0]
        eligible = self._eligible_factors(status)
        new_baseline = self._akamai_retry_baseline(
            status,
            target_device_id=target_device_id,
        )

        target_identity = {
            "user_ref": parent.target_identity.get("user_ref"),
            "username": username,
        }
        prepared_snapshot = {
            "account_present": status.account_present,
            "account_status": status.account_status,
            "business_state": status.business_state,
            "eligible_factor_count": len(eligible),
            "selected_factor": {
                "type": selected.type,
                "created_by": selected.created_by,
                "external_source": selected.external_source,
                "platform": selected.platform,
                "classification": selected.classification.value,
                "reset_eligible": selected.reset_eligible,
                # Retry mode never accepts a new device_ref from the caller.
                "device_ref": None,
            },
            "factor_summary": [
                {
                    "type": factor.type,
                    "created_by": factor.created_by,
                    "external_source": factor.external_source,
                    "platform": factor.platform,
                    "classification": factor.classification.value,
                    "reset_eligible": factor.reset_eligible,
                }
                for factor in status.factors
            ],
            "retry_child": True,
        }

        child = self.operations.create_retry_child(
            parent_operation_id=parent.operation_id,
            operation_type=AKAMAI_DEVICE_RESET,
            domain=AKAMAI_MFA_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            prepared_interaction_ref=interaction_ref,
            target_identity=target_identity,
            destructive_target={
                "device_id": target_device_id,
                "postcheck_factor_baseline": new_baseline,
            },
            prepared_snapshot=prepared_snapshot,
            request_id=request_id,
        )
        return RetryPreparation(
            parent=parent,
            child=child,
            safe_target=target_identity,
        )

    def prepare_retry(
        self,
        *,
        parent_operation_id: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> RetryPreparation:
        """Prepare a new child after explicit request for another attempt.

        This method is observational/preparatory only. It never calls a
        destructive primitive and it never confirms the child.
        """
        parent = self.operations.get(
            parent_operation_id,
            actor_context=actor_context,
            session_context=session_context,
        )
        if parent.status != OperationStatus.REQUIRES_RECONFIRMATION:
            raise OperationStateConflict(
                "retry preparation requires REQUIRES_RECONFIRMATION"
            )

        if parent.operation_type == EAA_OTP_RESET and parent.domain == EAA_DOMAIN:
            return self._prepare_eaa_retry(
                parent,
                actor_context=actor_context,
                session_context=session_context,
                interaction_ref=interaction_ref,
                request_id=request_id,
            )

        if (
            parent.operation_type == AKAMAI_DEVICE_RESET
            and parent.domain == AKAMAI_MFA_DOMAIN
        ):
            return self._prepare_akamai_retry(
                parent,
                actor_context=actor_context,
                session_context=session_context,
                interaction_ref=interaction_ref,
                request_id=request_id,
            )

        raise PrepareOperationError(
            "retry_operation_type_unsupported",
            "O tipo da operação anterior não suporta retry preparado.",
        )

    @staticmethod
    def _eligible_factors(status) -> list[ObservedFactor]:
        return [factor for factor in status.factors if factor.reset_eligible]

    def _resolve_selected_device(
        self,
        *,
        user_ref: str,
        device_ref: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        eligible: list[ObservedFactor],
    ) -> ObservedFactor:
        try:
            ref = self.references.resolve(
                device_ref,
                expected_type=ReferenceType.DEVICE,
                expected_domain=AKAMAI_MFA_DOMAIN,
                actor_context=actor_context,
                session_context=session_context,
            )
        except SafeReferenceError:
            raise

        ref_user = ref.target_identity.get("user_ref")
        if ref_user != user_ref:
            raise PrepareOperationError(
                "device_reference_target_mismatch",
                "A referência de dispositivo não pertence ao usuário informado.",
                status_code=403,
            )

        device_id = ref.internal_target.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise PrepareOperationError(
                "device_reference_invalid",
                "A referência de dispositivo não possui target interno válido.",
            )

        matches = [
            factor
            for factor in eligible
            if factor.internal.internal_device_id == device_id
        ]
        if len(matches) != 1:
            raise PrepareOperationError(
                "device_reference_stale",
                "O dispositivo selecionado não está mais elegível no estado atual.",
            )
        return matches[0]

    def prepare_akamai_mfa_device_reset(
        self,
        *,
        user_ref: str,
        device_ref: str | None,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        interaction_ref: str,
        request_id: str | None,
    ) -> PreparedOperation:
        identity_ref = self._resolve_user_ref(
            user_ref,
            actor_context=actor_context,
            session_context=session_context,
        )
        username = identity_ref.internal_target.get("username")
        if not isinstance(username, str) or not username.strip():
            raise PrepareOperationError(
                "target_revalidation_failed",
                "A referência de usuário não possui identidade revalidável.",
            )

        status = self.akamai_mfa_service.status_for_username(username)

        if not status.account_present:
            raise PrepareOperationError(
                "akamai_mfa_account_not_present",
                "O usuário não possui conta Akamai MFA.",
            )

        eligible = self._eligible_factors(status)

        if not eligible:
            if status.business_state == "already_awaiting_enrollment":
                raise PrepareOperationError(
                    "already_awaiting_enrollment",
                    "O usuário já está aguardando novo enrollment.",
                )
            raise PrepareOperationError(
                "no_eligible_authenticator",
                "Nenhum autenticador elegível foi encontrado.",
            )

        if device_ref:
            selected = self._resolve_selected_device(
                user_ref=user_ref,
                device_ref=device_ref,
                actor_context=actor_context,
                session_context=session_context,
                eligible=eligible,
            )
            selected_device_ref = device_ref
        else:
            if len(eligible) > 1:
                raise PrepareOperationError(
                    "device_selection_required",
                    "Há mais de um autenticador elegível; selecione uma referência segura.",
                )
            selected = eligible[0]
            selected_device_ref = None

        device_id = selected.internal.internal_device_id
        if not device_id:
            raise PrepareOperationError(
                "target_revalidation_failed",
                "O autenticador elegível não possui target interno utilizável.",
            )

        target_identity = {
            "user_ref": user_ref,
            "username": username,
        }
        prepared_snapshot = {
            "account_present": status.account_present,
            "account_status": status.account_status,
            "business_state": status.business_state,
            "eligible_factor_count": len(eligible),
            "selected_factor": {
                "type": selected.type,
                "created_by": selected.created_by,
                "external_source": selected.external_source,
                "platform": selected.platform,
                "classification": selected.classification.value,
                "reset_eligible": selected.reset_eligible,
                "device_ref": selected_device_ref,
            },
            "factor_summary": [
                {
                    "type": factor.type,
                    "created_by": factor.created_by,
                    "external_source": factor.external_source,
                    "platform": factor.platform,
                    "classification": factor.classification.value,
                    "reset_eligible": factor.reset_eligible,
                }
                for factor in status.factors
            ],
        }

        internal_factor_baseline = []
        for factor in status.factors:
            current_id = factor.internal.internal_device_id
            internal_factor_baseline.append(
                {
                    "device_id": current_id,
                    "is_target": current_id == device_id if current_id else False,
                    "classification": factor.classification.value,
                    "reset_eligible": factor.reset_eligible,
                    "type": factor.type,
                    "created_by": factor.created_by,
                    "external_source": factor.external_source,
                    "platform": factor.platform,
                }
            )

        op = self.operations.create_prepared(
            operation_type=AKAMAI_DEVICE_RESET,
            domain=AKAMAI_MFA_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            prepared_interaction_ref=interaction_ref,
            target_identity=target_identity,
            destructive_target={
                "device_id": device_id,
                "postcheck_factor_baseline": internal_factor_baseline,
            },
            prepared_snapshot=prepared_snapshot,
            request_id=request_id,
        )
        return PreparedOperation(operation=op, safe_target=target_identity)
