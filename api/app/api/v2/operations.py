from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...context import (
    InteractionContext,
    RequestContext,
    require_interaction_context,
    require_request_context,
)
from ...operations.execution import ExecutionBackendDisabled
from ...errors import UpstreamError
from ...operations.manager import OperationManager, PrepareOperationError
from ...operations.repository import (
    OperationContextMismatch,
    OperationExpired,
    OperationInteractionReuse,
    OperationNotFound,
    OperationRepository,
    OperationStateConflict,
)
from .dependencies import operation_manager, operation_repository, settings
from .errors import (
    map_execution_error,
    map_operation_error,
    map_prepare_error,
    map_upstream_error,
    request_id,
)
from .schemas import (
    OperationConfirmationResponse,
    OperationExecutionResponse,
    OperationStatusResponse,
    PreparedOperationResponse,
    RetryAlreadyCompletedResponse,
)


router = APIRouter(prefix="/v2/operations", tags=["operations-v2"])


@router.get(
    "/{operation_id}",
    response_model=OperationStatusResponse,
    summary="Consulta estado seguro de uma operação",
)
def get_operation_status(
    operation_id: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    repository: OperationRepository = Depends(operation_repository),
):
    try:
        op = repository.get(
            operation_id,
            actor_context=context.actor_context,
            session_context=context.session_context,
        )
    except (OperationNotFound, OperationContextMismatch) as exc:
        return map_operation_error(request, exc)

    return OperationStatusResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        status=op.status.value,
        target=dict(op.target_identity),
        prepared_snapshot=dict(op.prepared_snapshot),
        expires_at=op.expires_at,
        outcome_code=op.outcome_code,
        post_check_result=(
            dict(op.post_check_result) if op.post_check_result is not None else None
        ),
        simulation=(settings().execution_backend == "simulation"),
        request_id=request_id(request),
    )


@router.post(
    "/{parent_operation_id}/retry/prepare",
    response_model=PreparedOperationResponse | RetryAlreadyCompletedResponse,
    summary="Prepara child operation após reconfirmação ser requerida",
)
def prepare_retry_operation(
    parent_operation_id: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    interaction: InteractionContext = Depends(require_interaction_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        result = manager.prepare_retry(
            parent_operation_id=parent_operation_id,
            actor_context=context.actor_context,
            session_context=context.session_context,
            interaction_ref=interaction.interaction_ref,
            request_id=request_id(request),
        )
    except (
        OperationNotFound,
        OperationContextMismatch,
        OperationStateConflict,
    ) as exc:
        return map_operation_error(request, exc)
    except PrepareOperationError as exc:
        return map_prepare_error(request, exc)
    except UpstreamError as exc:
        return map_upstream_error(request, exc)

    if result.child is None:
        return RetryAlreadyCompletedResponse(
            operation_id=result.parent.operation_id,
            operation_type=result.parent.operation_type,
            domain=result.parent.domain,
            target=dict(result.safe_target),
            outcome_code=(
                result.parent.outcome_code
                or "retry_effect_already_present"
            ),
            request_id=request_id(request),
        )

    child = result.child
    return PreparedOperationResponse(
        operation_id=child.operation_id,
        operation_type=child.operation_type,
        domain=child.domain,
        target=dict(result.safe_target),
        expires_at=child.expires_at,
        request_id=request_id(request),
    )


@router.post(
    "/{operation_id}/confirm",
    response_model=OperationConfirmationResponse,
    summary="Confirma operação após interação humana posterior",
)
def confirm_operation(
    operation_id: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    interaction: InteractionContext = Depends(require_interaction_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        op = manager.confirm_operation(
            operation_id=operation_id,
            actor_context=context.actor_context,
            session_context=context.session_context,
            interaction_ref=interaction.interaction_ref,
            request_id=request_id(request),
        )
    except (
        OperationNotFound,
        OperationContextMismatch,
        OperationExpired,
        OperationInteractionReuse,
        OperationStateConflict,
    ) as exc:
        return map_operation_error(request, exc)

    assert op.confirmed_at is not None
    return OperationConfirmationResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        status="CONFIRMED",
        confirmed_at=op.confirmed_at,
        expires_at=op.expires_at,
        request_id=request_id(request),
    )


@router.post(
    "/{operation_id}/execute",
    response_model=OperationExecutionResponse,
    summary="Executa state machine usando backend interno configurado",
)
def execute_operation(
    operation_id: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        op = manager.execute_operation(
            operation_id=operation_id,
            actor_context=context.actor_context,
            session_context=context.session_context,
            request_id=request_id(request),
        )
    except (
        OperationNotFound,
        OperationContextMismatch,
        OperationExpired,
        OperationStateConflict,
        ExecutionBackendDisabled,
    ) as exc:
        return map_execution_error(request, exc)

    return OperationExecutionResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        status=op.status.value,
        outcome_code=op.outcome_code,
        post_check_result=(
            dict(op.post_check_result) if op.post_check_result is not None else None
        ),
        simulation=(settings().execution_backend == "simulation"),
        request_id=request_id(request),
    )


@router.post(
    "/{operation_id}/verify",
    response_model=OperationExecutionResponse,
    summary="Continua apenas a observação de uma operação VERIFYING",
)
def verify_operation(
    operation_id: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        op = manager.verify_operation(
            operation_id=operation_id,
            actor_context=context.actor_context,
            session_context=context.session_context,
            request_id=request_id(request),
        )
    except (
        OperationNotFound,
        OperationContextMismatch,
        OperationStateConflict,
        ExecutionBackendDisabled,
    ) as exc:
        return map_execution_error(request, exc)

    return OperationExecutionResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        status=op.status.value,
        outcome_code=op.outcome_code,
        post_check_result=(
            dict(op.post_check_result) if op.post_check_result is not None else None
        ),
        simulation=(settings().execution_backend == "simulation"),
        request_id=request_id(request),
    )
