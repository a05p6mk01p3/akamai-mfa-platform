from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ...errors import UpstreamError, UpstreamTimeout
from ...operations.execution import ExecutionBackendDisabled
from ...operations.manager import PrepareOperationError
from ...operations.repository import (
    OperationContextMismatch,
    OperationExpired,
    OperationInteractionReuse,
    OperationNotFound,
    OperationStateConflict,
)
from ...references.repository import (
    SafeReferenceContextMismatch,
    SafeReferenceExpired,
    SafeReferenceNotFound,
)


def request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def safe_error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": code,
            "message": message,
            "request_id": request_id(request),
        },
    )


def map_reference_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, SafeReferenceExpired):
        return safe_error(
            request,
            status_code=409,
            code="reference_expired",
            message="A referência expirou; repita a consulta.",
        )
    if isinstance(exc, SafeReferenceContextMismatch):
        return safe_error(
            request,
            status_code=403,
            code="reference_context_mismatch",
            message="A referência não pertence ao contexto atual.",
        )
    if isinstance(exc, SafeReferenceNotFound):
        return safe_error(
            request,
            status_code=404,
            code="reference_not_found",
            message="Referência não encontrada.",
        )
    return safe_error(
        request,
        status_code=400,
        code="invalid_reference",
        message="Referência inválida.",
    )


def map_prepare_error(request: Request, exc: PrepareOperationError) -> JSONResponse:
    return safe_error(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=str(exc),
    )


def map_operation_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, OperationContextMismatch):
        return safe_error(
            request,
            status_code=403,
            code="operation_context_mismatch",
            message="A operação não pertence ao contexto atual.",
        )
    if isinstance(exc, OperationNotFound):
        return safe_error(
            request,
            status_code=404,
            code="operation_not_found",
            message="Operação não encontrada.",
        )
    if isinstance(exc, OperationExpired):
        return safe_error(
            request,
            status_code=409,
            code="operation_expired",
            message="A operação expirou e não pode ser confirmada.",
        )
    if isinstance(exc, OperationInteractionReuse):
        return safe_error(
            request,
            status_code=409,
            code="confirmation_requires_later_interaction",
            message="A confirmação deve ocorrer em interação posterior ao prepare.",
        )
    if isinstance(exc, OperationStateConflict):
        return safe_error(
            request,
            status_code=409,
            code="operation_state_conflict",
            message="A operação não está em estado confirmável.",
        )
    return safe_error(
        request,
        status_code=409,
        code="operation_not_available",
        message="Operação indisponível.",
    )


def map_upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
    if isinstance(exc, UpstreamTimeout):
        return safe_error(
            request,
            status_code=504,
            code="upstream_timeout",
            message="Timeout ao consultar a API Akamai.",
        )
    if exc.status_code in (401, 403):
        return safe_error(
            request,
            status_code=502,
            code="upstream_auth_error",
            message="Falha de autorização na API Akamai.",
        )
    if exc.status_code == 429:
        return safe_error(
            request,
            status_code=503,
            code="upstream_rate_limited",
            message="API Akamai temporariamente limitada.",
        )
    return safe_error(
        request,
        status_code=502,
        code="upstream_error",
        message="Falha ao consultar a API Akamai.",
    )


def map_execution_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, ExecutionBackendDisabled):
        return safe_error(
            request,
            status_code=503,
            code="execution_backend_disabled",
            message="O framework de execução está desabilitado neste ambiente.",
        )
    return map_operation_error(request, exc)
