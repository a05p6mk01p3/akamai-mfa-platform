from __future__ import annotations

from ..services.akamai_mfa import AkamaiMfaService
from ..services.eaa import EaaService
from .execution import (
    AkamaiMfaTenantValidationExecutionAdapter,
    EaaTenantValidationExecutionAdapter,
    ExecutionAdapter,
    ExecutionBackendDisabled,
    PrimitiveResult,
    VerificationResult,
)
from .models import OperationRecord


class LiveExecutionAdapter:
    """Unified live execution gate with domain-local dispatch.

    Operator configuration decides only whether live destructive execution is
    enabled. The persisted operation type decides which domain adapter handles
    the primitive and its post-check. This preserves strict domain separation
    without exposing a per-domain operational mode switch.
    """

    enabled = True

    def __init__(
        self,
        *,
        eaa_service: EaaService,
        akamai_mfa_service: AkamaiMfaService,
    ) -> None:
        self._adapters: tuple[ExecutionAdapter, ...] = (
            EaaTenantValidationExecutionAdapter(eaa_service),
            AkamaiMfaTenantValidationExecutionAdapter(akamai_mfa_service),
        )

    def _adapter_for(self, operation: OperationRecord) -> ExecutionAdapter:
        matches = [adapter for adapter in self._adapters if adapter.supports(operation)]
        if len(matches) != 1:
            raise ExecutionBackendDisabled(
                "live execution backend does not support this operation type"
            )
        return matches[0]

    def supports(self, operation: OperationRecord) -> bool:
        return sum(1 for adapter in self._adapters if adapter.supports(operation)) == 1

    def mutate(self, operation: OperationRecord) -> PrimitiveResult:
        return self._adapter_for(operation).mutate(operation)

    def verify(self, operation: OperationRecord) -> VerificationResult:
        return self._adapter_for(operation).verify(operation)
