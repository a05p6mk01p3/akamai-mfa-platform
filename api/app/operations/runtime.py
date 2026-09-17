from __future__ import annotations

from ..config import Settings
from ..services.akamai_mfa import AkamaiMfaService
from ..services.eaa import EaaService
from .execution import (
    DisabledExecutionAdapter,
    ExecutionAdapter,
    SimulationExecutionAdapter,
)
from .live import LiveExecutionAdapter


def build_runtime_execution_adapter(
    settings: Settings,
    *,
    eaa_service: EaaService,
    akamai_mfa_service: AkamaiMfaService,
) -> ExecutionAdapter:
    """Build the runtime adapter from the operator-facing execution mode.

    `simulation` is non-destructive. `live` enables both domain adapters while
    preserving operation-type dispatch. `disabled` is fail-closed. Legacy
    per-domain backend names are intentionally not accepted by Settings.
    """

    if settings.execution_backend == "simulation":
        return SimulationExecutionAdapter(settings)
    if settings.execution_backend == "live":
        return LiveExecutionAdapter(
            eaa_service=eaa_service,
            akamai_mfa_service=akamai_mfa_service,
        )
    return DisabledExecutionAdapter()
