from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...context import RequestContext, require_request_context
from ...errors import UpstreamError
from ...references.service import SafeReferenceService
from ...services.eaa import EaaService
from .dependencies import eaa_service, reference_service
from .errors import map_upstream_error
from .schemas import EaaUserCandidateResponse, EaaUserSearchResponse


router = APIRouter(prefix="/v2/eaa", tags=["eaa-v2"])


@router.get(
    "/users/search",
    response_model=EaaUserSearchResponse,
    summary="Busca identidades EAA e emite referências seguras",
)
def search_eaa_users(
    request: Request,
    q: str = Query(min_length=1, max_length=256),
    context: RequestContext = Depends(require_request_context),
    service: EaaService = Depends(eaa_service),
    refs: SafeReferenceService = Depends(reference_service),
):
    query = q.strip()
    if not query:
        return EaaUserSearchResponse(
            status="not_found",
            query=q,
            count=0,
            total_count=0,
            refinement_required=False,
            candidates=[],
        )

    try:
        result = service.search(query)
    except UpstreamError as exc:
        return map_upstream_error(request, exc)

    candidates: list[EaaUserCandidateResponse] = []
    for candidate in result.candidates:
        referenced = refs.issue_user_ref(
            candidate.internal,
            candidate.safe,
            actor_context=context.actor_context,
            session_context=context.session_context,
        )
        candidates.append(
            EaaUserCandidateResponse(
                user_ref=referenced.reference.reference_id,
                username=candidate.safe.username,
                display_name=candidate.safe.display_name,
                status=candidate.safe.status,
                eaa_native_mfa_configured=candidate.safe.eaa_native_mfa_configured,
                otp_reset_available=candidate.safe.otp_reset_available,
            )
        )

    return EaaUserSearchResponse(
        status=result.result.value,
        query=query,
        count=len(candidates),
        total_count=result.total_count,
        refinement_required=result.refinement_required,
        candidates=candidates,
    )
