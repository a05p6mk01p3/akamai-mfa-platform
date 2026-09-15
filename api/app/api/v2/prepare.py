from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...context import (
    InteractionContext,
    RequestContext,
    require_interaction_context,
    require_request_context,
)
from ...errors import UpstreamError
from ...operations.manager import OperationManager, PrepareOperationError
from ...references.repository import SafeReferenceError
from .dependencies import operation_manager
from .errors import (
    map_prepare_error,
    map_reference_error,
    map_upstream_error,
    request_id,
)
from .schemas import (
    AkamaiDeviceResetPrepareRequest,
    EaaOtpPrepareRequest,
    PreparedOperationResponse,
)


router = APIRouter(tags=["prepare-v2"])


@router.post(
    "/v2/eaa-native-mfa/otp-reset/prepare",
    response_model=PreparedOperationResponse,
    summary="Prepara reset de OTP EAA Native MFA sem executar mutação",
)
def prepare_eaa_otp_reset(
    payload: EaaOtpPrepareRequest,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    interaction: InteractionContext = Depends(require_interaction_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        prepared = manager.prepare_eaa_otp_reset(
            user_ref=payload.user_ref,
            actor_context=context.actor_context,
            session_context=context.session_context,
            interaction_ref=interaction.interaction_ref,
            request_id=request_id(request),
        )
    except SafeReferenceError as exc:
        return map_reference_error(request, exc)
    except PrepareOperationError as exc:
        return map_prepare_error(request, exc)
    except UpstreamError as exc:
        return map_upstream_error(request, exc)

    op = prepared.operation
    return PreparedOperationResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        target=dict(prepared.safe_target),
        expires_at=op.expires_at,
        request_id=request_id(request),
    )


@router.post(
    "/v2/akamai-mfa/device-reset/prepare",
    response_model=PreparedOperationResponse,
    summary="Prepara reset de um autenticador Akamai MFA sem executar DELETE",
)
def prepare_akamai_mfa_device_reset(
    payload: AkamaiDeviceResetPrepareRequest,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    interaction: InteractionContext = Depends(require_interaction_context),
    manager: OperationManager = Depends(operation_manager),
):
    try:
        prepared = manager.prepare_akamai_mfa_device_reset(
            user_ref=payload.user_ref,
            device_ref=payload.device_ref,
            actor_context=context.actor_context,
            session_context=context.session_context,
            interaction_ref=interaction.interaction_ref,
            request_id=request_id(request),
        )
    except SafeReferenceError as exc:
        return map_reference_error(request, exc)
    except PrepareOperationError as exc:
        return map_prepare_error(request, exc)
    except UpstreamError as exc:
        return map_upstream_error(request, exc)

    op = prepared.operation
    return PreparedOperationResponse(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        domain=op.domain,
        target=dict(prepared.safe_target),
        expires_at=op.expires_at,
        request_id=request_id(request),
    )
