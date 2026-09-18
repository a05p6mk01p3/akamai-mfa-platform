from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol

from ..config import Settings
from ..errors import UpstreamError, UpstreamTimeout
from ..services.eaa import EaaService
from ..services.akamai_mfa import AkamaiMfaService
from .models import OperationRecord


class PrimitiveDisposition(StrEnum):
    EXPECTED = "expected"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


class VerificationDisposition(StrEnum):
    EXPECTED_STATE = "expected_state"
    TARGET_REMAINS = "target_remains"
    INCONCLUSIVE = "inconclusive"
    WRONG_STATE = "wrong_state"


@dataclass(frozen=True)
class PrimitiveResult:
    disposition: PrimitiveDisposition
    safe_code: str
    safe_details: Mapping[str, Any]


@dataclass(frozen=True)
class VerificationResult:
    disposition: VerificationDisposition
    safe_code: str
    safe_details: Mapping[str, Any]


class ExecutionAdapter(Protocol):
    enabled: bool

    def supports(self, operation: OperationRecord) -> bool:
        ...

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        ...

    def verify(self, operation: OperationRecord) -> VerificationResult:
        ...


class ExecutionBackendDisabled(RuntimeError):
    pass


class DisabledExecutionAdapter:
    enabled = False

    def supports(self, operation: OperationRecord) -> bool:
        return False

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        raise ExecutionBackendDisabled("execution backend disabled")

    def verify(self, operation: OperationRecord) -> VerificationResult:
        raise ExecutionBackendDisabled("execution backend disabled")


class SimulationExecutionAdapter:
    """Pure simulation. Performs no HTTP call and no external mutation."""

    enabled = True

    def supports(self, operation: OperationRecord) -> bool:
        return operation.operation_type in {
            "EAA_NATIVE_MFA_OTP_RESET",
            "AKAMAI_MFA_DEVICE_RESET",
        }

    def __init__(self, settings: Settings) -> None:
        if settings.execution_backend != "simulation":
            raise ExecutionBackendDisabled("simulation backend not enabled")
        self.primitive_outcome = settings.simulation_primitive_outcome
        self.postcheck_outcome = settings.simulation_postcheck_outcome

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        if self.primitive_outcome == "expected":
            return PrimitiveResult(
                PrimitiveDisposition.EXPECTED,
                "SIMULATION_PRIMITIVE_EXPECTED",
                {"simulation": True, "external_mutation_performed": False},
            )
        if self.primitive_outcome == "ambiguous":
            return PrimitiveResult(
                PrimitiveDisposition.AMBIGUOUS,
                "SIMULATION_PRIMITIVE_AMBIGUOUS",
                {"simulation": True, "external_mutation_performed": False},
            )
        return PrimitiveResult(
            PrimitiveDisposition.FAILED,
            "SIMULATION_PRIMITIVE_FAILED",
            {"simulation": True, "external_mutation_performed": False},
        )

    def verify(self, operation: OperationRecord) -> VerificationResult:
        mapping = {
            "expected": (
                VerificationDisposition.EXPECTED_STATE,
                "SIMULATION_POSTCHECK_EXPECTED",
            ),
            "target_remains": (
                VerificationDisposition.TARGET_REMAINS,
                "SIMULATION_POSTCHECK_TARGET_REMAINS",
            ),
            "inconclusive": (
                VerificationDisposition.INCONCLUSIVE,
                "SIMULATION_POSTCHECK_INCONCLUSIVE",
            ),
            "wrong_state": (
                VerificationDisposition.WRONG_STATE,
                "SIMULATION_POSTCHECK_WRONG_STATE",
            ),
        }
        disposition, code = mapping[self.postcheck_outcome]
        return VerificationResult(
            disposition,
            code,
            {
                "simulation": True,
                "observation_source": "simulation",
                "external_mutation_performed": False,
            },
        )



class EaaTenantValidationExecutionAdapter:
    """Controlled tenant-validation adapter for the EAA OTP primitive.

    It can issue one real EAA OTP reset POST. It deliberately never reports a
    successful post-check because the exact tenant post-reset state has not yet
    been frozen. Observation remains EAA-only and returns INCONCLUSIVE with safe
    fields until that criterion is validated.
    """

    enabled = True

    def __init__(self, service: EaaService) -> None:
        self.service = service

    def supports(self, operation: OperationRecord) -> bool:
        return operation.operation_type == "EAA_NATIVE_MFA_OTP_RESET"

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        target = dict(operation.destructive_target or {})
        reset_id = target.get("eaa_reset_id")
        if not isinstance(reset_id, str) or not reset_id:
            return PrimitiveResult(
                PrimitiveDisposition.FAILED,
                "EAA_RESET_TARGET_MISSING",
                {
                    "external_mutation_performed": False,
                    "domain": "eaa_native_mfa",
                },
            )

        try:
            status_code = self.service.reset_otp(reset_id)
        except UpstreamTimeout:
            return PrimitiveResult(
                PrimitiveDisposition.AMBIGUOUS,
                "EAA_OTP_RESET_TRANSPORT_AMBIGUOUS",
                {
                    "external_mutation_performed": "unknown",
                    "domain": "eaa_native_mfa",
                    "transport": "timeout",
                },
            )
        except UpstreamError as exc:
            status = exc.status_code
            if status is None or status >= 500:
                return PrimitiveResult(
                    PrimitiveDisposition.AMBIGUOUS,
                    "EAA_OTP_RESET_TRANSPORT_AMBIGUOUS",
                    {
                        "external_mutation_performed": "unknown",
                        "domain": "eaa_native_mfa",
                        "upstream_status": status,
                    },
                )
            return PrimitiveResult(
                PrimitiveDisposition.FAILED,
                "EAA_OTP_RESET_REJECTED",
                {
                    "external_mutation_performed": False,
                    "domain": "eaa_native_mfa",
                    "upstream_status": status,
                },
            )

        return PrimitiveResult(
            PrimitiveDisposition.EXPECTED,
            "EAA_OTP_RESET_UPSTREAM_ACCEPTED",
            {
                "external_mutation_performed": True,
                "domain": "eaa_native_mfa",
                "upstream_status": status_code,
            },
        )

    def verify(self, operation: OperationRecord) -> VerificationResult:
        username = operation.target_identity.get("username")
        if not isinstance(username, str) or not username:
            return VerificationResult(
                VerificationDisposition.INCONCLUSIVE,
                "EAA_POSTCHECK_IDENTITY_UNAVAILABLE",
                {
                    "domain": "eaa_native_mfa",
                    "success_criterion_validated": False,
                },
            )

        try:
            observation = self.service.observe_otp(username)
        except (UpstreamTimeout, UpstreamError):
            return VerificationResult(
                VerificationDisposition.INCONCLUSIVE,
                "EAA_POSTCHECK_UNAVAILABLE",
                {
                    "domain": "eaa_native_mfa",
                    "success_criterion_validated": False,
                },
            )

        return VerificationResult(
            VerificationDisposition.INCONCLUSIVE,
            "EAA_POSTCHECK_TENANT_VALIDATION_REQUIRED",
            {
                "domain": "eaa_native_mfa",
                "success_criterion_validated": False,
                "exact_identity": observation.exact_identity,
                "username_matches": (
                    observation.username.casefold() == username.casefold()
                    if observation.username
                    else False
                ),
                "status": observation.status,
                "login_mfa": observation.login_mfa,
                "otp_reset_available": observation.otp_reset_available,
                "akamai_mfa_observed": False,
                "automatic_retry_performed": False,
            },
        )


class AkamaiMfaTenantValidationExecutionAdapter:
    """Controlled real device DELETE with an objective, domain-local post-check."""

    enabled = True

    def __init__(self, service: AkamaiMfaService) -> None:
        self.service = service

    def supports(self, operation: OperationRecord) -> bool:
        return operation.operation_type == "AKAMAI_MFA_DEVICE_RESET"

    @staticmethod
    def _safe_factor_signature(factor: Any) -> tuple[Any, ...]:
        return (
            factor.type,
            factor.created_by,
            factor.external_source,
            factor.platform,
            factor.classification.value,
            factor.reset_eligible,
        )

    @staticmethod
    def _baseline_signature(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            item.get("type"),
            item.get("created_by"),
            item.get("external_source"),
            item.get("platform"),
            item.get("classification"),
            item.get("reset_eligible"),
        )

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        target = dict(operation.destructive_target or {})
        device_id = target.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return PrimitiveResult(
                PrimitiveDisposition.FAILED,
                "AKAMAI_MFA_DEVICE_TARGET_MISSING",
                {
                    "domain": "akamai_mfa",
                    "external_mutation_performed": False,
                },
            )

        try:
            status_code = self.service.delete_device(device_id)
        except UpstreamTimeout:
            return PrimitiveResult(
                PrimitiveDisposition.AMBIGUOUS,
                "AKAMAI_MFA_DELETE_TRANSPORT_AMBIGUOUS",
                {
                    "domain": "akamai_mfa",
                    "transport": "timeout",
                    "external_mutation_performed": "unknown",
                    "automatic_retry_performed": False,
                },
            )
        except UpstreamError as exc:
            status = exc.status_code
            # 404 can mean a concurrent removal after successful preflight.
            # 5xx/unknown transport may have occurred after upstream mutation.
            if status is None or status == 404 or status >= 500:
                return PrimitiveResult(
                    PrimitiveDisposition.AMBIGUOUS,
                    "AKAMAI_MFA_DELETE_TRANSPORT_AMBIGUOUS",
                    {
                        "domain": "akamai_mfa",
                        "upstream_status": status,
                        "external_mutation_performed": "unknown",
                        "automatic_retry_performed": False,
                    },
                )
            return PrimitiveResult(
                PrimitiveDisposition.FAILED,
                "AKAMAI_MFA_DELETE_REJECTED",
                {
                    "domain": "akamai_mfa",
                    "upstream_status": status,
                    "external_mutation_performed": False,
                    "automatic_retry_performed": False,
                },
            )

        if status_code == 204:
            return PrimitiveResult(
                PrimitiveDisposition.EXPECTED,
                "AKAMAI_MFA_DELETE_204",
                {
                    "domain": "akamai_mfa",
                    "upstream_status": 204,
                    "external_mutation_performed": True,
                    "automatic_retry_performed": False,
                },
            )

        # The frozen tenant contract expects exactly 204. Any other successful
        # transport code may still have mutated state, so inspect before deciding.
        return PrimitiveResult(
            PrimitiveDisposition.AMBIGUOUS,
            "AKAMAI_MFA_DELETE_UNEXPECTED_SUCCESS_STATUS",
            {
                "domain": "akamai_mfa",
                "upstream_status": status_code,
                "external_mutation_performed": "unknown",
                "automatic_retry_performed": False,
            },
        )

    def verify(self, operation: OperationRecord) -> VerificationResult:
        target = dict(operation.destructive_target or {})
        target_device_id = target.get("device_id")
        baseline = target.get("postcheck_factor_baseline")
        username = operation.target_identity.get("username")

        if (
            not isinstance(target_device_id, str)
            or not target_device_id
            or not isinstance(username, str)
            or not username
            or not isinstance(baseline, list)
        ):
            return VerificationResult(
                VerificationDisposition.INCONCLUSIVE,
                "AKAMAI_MFA_POSTCHECK_BASELINE_UNAVAILABLE",
                {
                    "domain": "akamai_mfa",
                    "automatic_retry_performed": False,
                },
            )

        try:
            status = self.service.status_for_username(username)
        except (UpstreamTimeout, UpstreamError, ValueError):
            return VerificationResult(
                VerificationDisposition.INCONCLUSIVE,
                "AKAMAI_MFA_POSTCHECK_UNAVAILABLE",
                {
                    "domain": "akamai_mfa",
                    "automatic_retry_performed": False,
                },
            )

        if not status.account_present:
            return VerificationResult(
                VerificationDisposition.WRONG_STATE,
                "AKAMAI_MFA_ACCOUNT_REMOVED_UNEXPECTEDLY",
                {
                    "domain": "akamai_mfa",
                    "account_present": False,
                    "target_absent": True,
                    "protected_factors_preserved": False,
                    "non_target_factors_preserved": False,
                    "automatic_retry_performed": False,
                },
            )

        current_by_id = {
            factor.internal.internal_device_id: factor
            for factor in status.factors
            if factor.internal.internal_device_id
        }
        target_absent = target_device_id not in current_by_id

        baseline_non_target = [
            item
            for item in baseline
            if isinstance(item, dict) and not item.get("is_target")
        ]
        baseline_protected = [
            item
            for item in baseline_non_target
            if not bool(item.get("reset_eligible"))
        ]

        missing_non_target_ids = []
        missing_non_target_signatures = []

        # Strong identity check where an upstream ID exists.
        for item in baseline_non_target:
            baseline_id = item.get("device_id")
            if isinstance(baseline_id, str) and baseline_id:
                if baseline_id not in current_by_id:
                    missing_non_target_ids.append(baseline_id)
            else:
                signature = self._baseline_signature(item)
                if not any(
                    self._safe_factor_signature(factor) == signature
                    for factor in status.factors
                ):
                    missing_non_target_signatures.append(signature)

        protected_missing = False
        for item in baseline_protected:
            baseline_id = item.get("device_id")
            if isinstance(baseline_id, str) and baseline_id:
                if baseline_id not in current_by_id:
                    protected_missing = True
                    break
            else:
                signature = self._baseline_signature(item)
                if not any(
                    self._safe_factor_signature(factor) == signature
                    for factor in status.factors
                ):
                    protected_missing = True
                    break

        non_target_preserved = not missing_non_target_ids and not missing_non_target_signatures
        protected_preserved = not protected_missing

        safe_details = {
            "domain": "akamai_mfa",
            "account_present": True,
            "account_status": status.account_status,
            "target_absent": target_absent,
            "non_target_factors_preserved": non_target_preserved,
            "protected_factors_preserved": protected_preserved,
            "current_factor_count": len(status.factors),
            "protected_factor_count": sum(
                1 for factor in status.factors if not factor.reset_eligible
            ),
            "automatic_retry_performed": False,
        }

        if not non_target_preserved or not protected_preserved:
            return VerificationResult(
                VerificationDisposition.WRONG_STATE,
                "AKAMAI_MFA_POSTCHECK_FACTOR_LOSS",
                safe_details,
            )

        if target_absent:
            return VerificationResult(
                VerificationDisposition.EXPECTED_STATE,
                "AKAMAI_MFA_POSTCHECK_TARGET_ABSENT",
                safe_details,
            )

        return VerificationResult(
            VerificationDisposition.TARGET_REMAINS,
            "AKAMAI_MFA_POSTCHECK_TARGET_REMAINS",
            safe_details,
        )
