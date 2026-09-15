from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...context import RequestContext, require_request_context
from ...errors import UpstreamError
from ...references.repository import SafeReferenceError
from ...references.service import SafeReferenceService
from ...services.akamai_mfa import AkamaiMfaService
from .dependencies import akamai_mfa_service, reference_service
from .errors import map_reference_error, map_upstream_error
from .schemas import AkamaiMfaFactorResponse, AkamaiMfaStatusResponse


router = APIRouter(prefix="/v2/akamai-mfa", tags=["akamai-mfa-v2"])


@router.get(
    "/users/{user_ref}/status",
    response_model=AkamaiMfaStatusResponse,
    summary="Consulta estado Akamai MFA por referência segura",
)
def get_akamai_mfa_status(
    user_ref: str,
    request: Request,
    context: RequestContext = Depends(require_request_context),
    service: AkamaiMfaService = Depends(akamai_mfa_service),
    refs: SafeReferenceService = Depends(reference_service),
):
    try:
        identity_ref = refs.resolve_user_ref(
            user_ref,
            actor_context=context.actor_context,
            session_context=context.session_context,
        )
    except SafeReferenceError as exc:
        return map_reference_error(request, exc)

    username = identity_ref.internal_target.get("username")
    if not isinstance(username, str) or not username.strip():
        return map_reference_error(request, ValueError("invalid internal user reference"))

    try:
        status = service.status_for_username(username)
    except UpstreamError as exc:
        return map_upstream_error(request, exc)
    except ValueError:
        from .errors import safe_error
        return safe_error(
            request,
            status_code=409,
            code="ambiguous_akamai_mfa_account",
            message="A conta Akamai MFA não pôde ser resolvida de forma inequívoca.",
        )

    target_identity = {
        "user_ref": user_ref,
        "username": username,
    }
    referenced_factors = refs.reference_status_factors(
        status,
        actor_context=context.actor_context,
        session_context=context.session_context,
        target_identity=target_identity,
    )

    factors = [
        AkamaiMfaFactorResponse(
            type=item.factor.type,
            created_by=item.factor.created_by,
            external_source=item.factor.external_source,
            platform=item.factor.platform,
            classification=item.factor.classification.value,
            reset_eligible=item.factor.reset_eligible,
            device_ref=item.device_ref,
        )
        for item in referenced_factors
    ]
    eligible_count = sum(1 for factor in factors if factor.reset_eligible)

    return AkamaiMfaStatusResponse(
        user_ref=user_ref,
        account_present=status.account_present,
        account_status=status.account_status,
        business_state=status.business_state,
        eligible_factor_count=eligible_count,
        selection_required=eligible_count > 1,
        factors=factors,
    )
