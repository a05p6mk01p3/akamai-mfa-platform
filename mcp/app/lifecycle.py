from __future__ import annotations

from typing import Any

from .attestation import (
    PreparedInteractionAlreadyClaimed,
    PreparedInteractionExpired,
    PreparedInteractionContextMismatch,
    PreparedInteractionLaterRequired,
    PreparedInteractionRegistry,
    PreparedInteractionTypeMismatch,
    PreparedInteractionUnknown,
)
from .backend import BackendError, MfaApiClient
from .tools import (
    map_confirmation_result,
    map_execution_result,
    map_operation_observation,
    safe_backend_error,
)


def local_lifecycle_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PreparedInteractionExpired):
        code = "prepared_operation_expired"
    elif isinstance(exc, PreparedInteractionUnknown):
        code = "prepared_interaction_context_unavailable"
    elif isinstance(exc, PreparedInteractionContextMismatch):
        code = "operation_context_mismatch"
    elif isinstance(exc, PreparedInteractionTypeMismatch):
        code = "operation_domain_mismatch"
    elif isinstance(exc, PreparedInteractionLaterRequired):
        code = "later_human_confirmation_required"
    elif isinstance(exc, PreparedInteractionAlreadyClaimed):
        code = "operation_locally_consumed"
    else:
        code = "operation_not_available"
    return {"status": "blocked", "code": code, "message": str(exc)}


async def observe_after_transport_uncertainty(
    *,
    client: MfaApiClient,
    operation_id: str,
    context: Any,
    expected_operation_type: str,
    expected_domain: str,
    phase: str,
) -> dict[str, Any]:
    try:
        body = await client.get_operation_status(operation_id, context=context)
    except BackendError:
        return {
            "status": "unknown",
            "code": f"{phase}_result_ambiguous",
            "operation_id": operation_id,
            "automatic_destructive_retry_performed": False,
            "message": (
                "O resultado não pôde ser observado com segurança. Não repita a "
                "operação automaticamente; inspecione o estado antes de nova decisão."
            ),
        }
    observed = map_operation_observation(
        body,
        operation_id=operation_id,
        expected_operation_type=expected_operation_type,
        expected_domain=expected_domain,
    )
    observed["code"] = f"{phase}_transport_observed"
    observed["message"] = (
        "Houve incerteza de transporte; o MCP fez somente observação do estado e "
        "não repetiu confirm/execute automaticamente."
    )
    return observed


async def confirm_then_execute(
    *,
    client: MfaApiClient,
    registry: PreparedInteractionRegistry,
    destructive_execution_enabled: bool,
    operation_id: str,
    context: Any,
    expected_operation_type: str,
    expected_domain: str,
) -> dict[str, Any]:
    try:
        registry.require_later_interaction(
            operation_id=operation_id,
            context=context,
            expected_operation_type=expected_operation_type,
            expected_domain=expected_domain,
        )
    except Exception as exc:
        return local_lifecycle_error(exc)

    if not destructive_execution_enabled:
        return {
            "status": "not_available",
            "code": "destructive_execution_disabled_in_cs04",
            "operation_id": operation_id,
            "message": (
                "O gate de interação posterior foi validado, mas chamadas API "
                "confirm/execute estão desabilitadas por configuração neste processo MCP."
            ),
        }

    try:
        registry.claim_for_reset(
            operation_id=operation_id,
            context=context,
            expected_operation_type=expected_operation_type,
            expected_domain=expected_domain,
        )
    except Exception as exc:
        return local_lifecycle_error(exc)

    try:
        confirm_body = await client.confirm_operation(operation_id, context=context)
    except BackendError as exc:
        if exc.code in {"backend_timeout", "backend_connection_error"}:
            observed = await observe_after_transport_uncertainty(
                client=client,
                operation_id=operation_id,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
                phase="confirmation",
            )
            if observed.get("status") == "PREPARED":
                registry.release_claim(operation_id)
            else:
                registry.mark_terminal(operation_id)
            return observed
        registry.mark_terminal(operation_id)
        return safe_backend_error(exc)

    confirmation = map_confirmation_result(
        confirm_body,
        operation_id=operation_id,
        expected_operation_type=expected_operation_type,
        expected_domain=expected_domain,
    )
    if confirmation.get("status") != "CONFIRMED":
        registry.mark_terminal(operation_id)
        return confirmation

    try:
        execute_body = await client.execute_operation(operation_id, context=context)
    except BackendError as exc:
        registry.mark_terminal(operation_id)
        if exc.code in {"backend_timeout", "backend_connection_error"}:
            return await observe_after_transport_uncertainty(
                client=client,
                operation_id=operation_id,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
                phase="execution",
            )
        return safe_backend_error(exc)

    registry.mark_terminal(operation_id)
    return map_execution_result(
        execute_body,
        operation_id=operation_id,
        expected_operation_type=expected_operation_type,
        expected_domain=expected_domain,
    )
