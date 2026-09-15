from __future__ import annotations

import logging
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__
from .attestation import PreparedInteractionRegistry
from .backend import BackendError, MfaApiClient
from .config import Settings
from .lifecycle import confirm_then_execute
from .context import (
    RequestBoundContextProvider,
    TrustedContextUnavailable,
    TrustedIngressUnavailable,
    interaction_fingerprint,
)
from .tools import (
    map_akamai_status,
    map_prepare_result,
    map_search_result,
    safe_backend_error,
)
from .validation import (
    normalize_device_ref,
    normalize_operation_id,
    normalize_query,
    normalize_user_ref,
)

settings = Settings.from_env()
logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger("akamai_mfa_mcp")
client = MfaApiClient(settings.api_url, settings.api_timeout)
context_provider = RequestBoundContextProvider(settings)
prepared_interactions = PreparedInteractionRegistry()

mcp = MCPServer(
    "Akamai MFA Platform",
    version=__version__,
    instructions=(
        "MCP v2 da plataforma Akamai MFA. EAA Native MFA OTP e Akamai MFA são "
        "domínios independentes. CS06 autentica o ingress confiável antes de "
        "aceitar actor/session request-bound e preserva o lifecycle "
        "confirm->execute somente após interação humana posterior. "
        "Não há retry destrutivo cego."
    ),
    log_level=settings.log_level,
)


def _context_or_error(
    ctx: Context | None,
    *,
    require_interaction: bool = False,
) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        context = context_provider.current(
            ctx,
            require_interaction=require_interaction,
        )
    except TrustedIngressUnavailable as exc:
        if settings.log_attestation_probe:
            logger.info(
                "trusted_ingress mode=%s authenticated=False",
                settings.trusted_ingress_mode,
            )
        return None, {
            "status": "error",
            "code": "trusted_ingress_unavailable",
            "message": str(exc),
        }
    except TrustedContextUnavailable as exc:
        return None, {
            "status": "error",
            "code": "interaction_context_unavailable"
            if require_interaction
            else "trusted_context_unavailable",
            "message": str(exc),
        }

    if settings.log_attestation_probe:
        logger.info(
            "trusted_ingress mode=%s authenticated=%s",
            settings.trusted_ingress_mode,
            settings.trusted_ingress_mode == "shared_secret",
        )
        fingerprint = (
            interaction_fingerprint(context.interaction_ref)
            if context.interaction_ref is not None
            else "none"
        )
        actor_fp = interaction_fingerprint(context.actor)
        session_fp = interaction_fingerprint(context.session)
        logger.info(
            "trusted_context actor_source=%s actor_fingerprint=%s "
            "session_source=%s session_fingerprint=%s",
            context.actor_source or "unknown",
            actor_fp,
            context.session_source or "unknown",
            session_fp,
        )
        logger.info(
            "interaction_attestation present=%s source=%s fingerprint=%s "
            "stateless_session_id_present=%s",
            context.interaction_ref is not None,
            context.interaction_source or "none",
            fingerprint,
            bool(getattr(ctx, "session_id", None)) if ctx is not None else False,
        )
    return context, None



@mcp.tool(
    title="Buscar identidade no Akamai EAA",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
async def search_eaa_user(
    query: Annotated[
        str,
        Field(
            description=(
                "Texto de busca da identidade EAA; pode ser username, "
                "samAccountName ou nome."
            ),
            min_length=1,
            max_length=256,
        ),
    ],
    ctx: Context,
) -> dict[str, Any]:
    """Busca EAA read-only preservando found / ambiguous / not_found."""
    query = normalize_query(query)
    context, error = _context_or_error(ctx)
    if error:
        return error
    try:
        body = await client.search_eaa_user(query, context=context)
    except BackendError as exc:
        logger.warning(
            "search_eaa_user backend error status=%s code=%s",
            exc.status_code,
            exc.code,
        )
        return safe_backend_error(exc)
    return map_search_result(body)


@mcp.tool(
    title="Preparar reset do EAA Native MFA OTP",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        open_world_hint=False,
    ),
)
async def prepare_eaa_otp_reset(
    ctx: Context,
    user_ref: Annotated[
        str | None,
        Field(description="user_ref opaco retornado por search_eaa_user."),
    ] = None,
    parent_operation_id: Annotated[
        str | None,
        Field(
            description=(
                "operation_id pai em REQUIRES_RECONFIRMATION "
                "para retry explícito."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Prepara operação sem mutação; retry usa somente parent_operation_id."""
    if parent_operation_id is not None:
        parent_operation_id = normalize_operation_id(parent_operation_id)
        if user_ref is not None:
            return {
                "status": "error",
                "code": "invalid_prepare_arguments",
                "message": (
                    "Retry por parent_operation_id não aceita user_ref. "
                    "O target é revalidado pela API."
                ),
            }
    else:
        if user_ref is None:
            return {
                "status": "error",
                "code": "user_ref_required",
                "message": "user_ref é obrigatório para um novo prepare EAA.",
            }
        user_ref = normalize_user_ref(user_ref)

    context, error = _context_or_error(ctx, require_interaction=True)
    if error:
        return error

    try:
        if parent_operation_id is not None:
            body = await client.prepare_retry(
                parent_operation_id,
                context=context,
            )
        else:
            assert user_ref is not None
            body = await client.prepare_eaa_otp_reset(
                user_ref,
                context=context,
            )
    except BackendError as exc:
        logger.warning(
            "prepare_eaa_otp_reset backend error status=%s code=%s",
            exc.status_code,
            exc.code,
        )
        return safe_backend_error(exc)

    result = map_prepare_result(body)
    if result.get("status") == "prepared":
        try:
            prepared_interactions.record(
                operation_id=result["operation_id"],
                operation_type=result["operation_type"],
                domain=result["domain"],
                context=context,
                expires_at=result.get("expires_at"),
            )
        except RuntimeError:
            return {
                "status": "error",
                "code": "prepared_interaction_registry_unavailable",
                "message": (
                    "A API preparou a operação, mas o MCP não conseguiu registrar "
                    "a correlação de interação. Não tente executar esta operação."
                ),
                "operation_id": result.get("operation_id"),
            }
    return result


@mcp.tool(
    title="Executar reset do EAA Native MFA OTP",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def reset_eaa_otp(
    operation_id: Annotated[
        str,
        Field(
            description=(
                "operation_id opaco de uma operação EAA OTP já preparada."
            ),
        ),
    ],
    ctx: Context,
) -> dict[str, Any]:
    """Confirma e executa EAA somente após interação humana posterior."""
    operation_id = normalize_operation_id(operation_id)
    context, error = _context_or_error(ctx, require_interaction=True)
    if error:
        return error
    return await confirm_then_execute(
        client=client,
        registry=prepared_interactions,
        destructive_execution_enabled=(settings.destructive_execution_mode == "enabled"),
        operation_id=operation_id,
        context=context,
        expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
        expected_domain="eaa_native_mfa",
    )


@mcp.tool(
    title="Consultar estado Akamai MFA",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
async def get_akamai_mfa_status(
    user_ref: Annotated[
        str,
        Field(description="user_ref opaco retornado por search_eaa_user."),
    ],
    ctx: Context,
) -> dict[str, Any]:
    """Consulta fatores sem recomputar elegibilidade no MCP."""
    user_ref = normalize_user_ref(user_ref)
    context, error = _context_or_error(ctx)
    if error:
        return error
    try:
        body = await client.get_akamai_mfa_status(
            user_ref,
            context=context,
        )
    except BackendError as exc:
        logger.warning(
            "get_akamai_mfa_status backend error status=%s code=%s",
            exc.status_code,
            exc.code,
        )
        return safe_backend_error(exc)
    return map_akamai_status(body)


@mcp.tool(
    title="Preparar reset de dispositivo Akamai MFA",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        open_world_hint=False,
    ),
)
async def prepare_akamai_mfa_device_reset(
    ctx: Context,
    user_ref: Annotated[
        str | None,
        Field(description="user_ref opaco da identidade selecionada."),
    ] = None,
    device_ref: Annotated[
        str | None,
        Field(
            description=(
                "device_ref opaco somente quando seleção explícita "
                "for necessária."
            ),
        ),
    ] = None,
    parent_operation_id: Annotated[
        str | None,
        Field(
            description=(
                "operation_id pai em REQUIRES_RECONFIRMATION "
                "para retry explícito."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Prepara reset de um único fator elegível; não executa DELETE."""
    if parent_operation_id is not None:
        parent_operation_id = normalize_operation_id(parent_operation_id)
        if user_ref is not None or device_ref is not None:
            return {
                "status": "error",
                "code": "invalid_prepare_arguments",
                "message": (
                    "Retry por parent_operation_id não aceita user_ref/device_ref. "
                    "A API preserva e revalida o target anterior."
                ),
            }
    else:
        if user_ref is None:
            return {
                "status": "error",
                "code": "user_ref_required",
                "message": "user_ref é obrigatório para um novo prepare Akamai MFA.",
            }
        user_ref = normalize_user_ref(user_ref)
        if device_ref is not None:
            device_ref = normalize_device_ref(device_ref)

    context, error = _context_or_error(ctx, require_interaction=True)
    if error:
        return error

    try:
        if parent_operation_id is not None:
            body = await client.prepare_retry(
                parent_operation_id,
                context=context,
            )
        else:
            assert user_ref is not None
            body = await client.prepare_akamai_mfa_device_reset(
                user_ref,
                device_ref,
                context=context,
            )
    except BackendError as exc:
        logger.warning(
            "prepare_akamai_mfa_device_reset backend error status=%s code=%s",
            exc.status_code,
            exc.code,
        )
        return safe_backend_error(exc)

    result = map_prepare_result(body)
    if result.get("status") == "prepared":
        try:
            prepared_interactions.record(
                operation_id=result["operation_id"],
                operation_type=result["operation_type"],
                domain=result["domain"],
                context=context,
                expires_at=result.get("expires_at"),
            )
        except RuntimeError:
            return {
                "status": "error",
                "code": "prepared_interaction_registry_unavailable",
                "message": (
                    "A API preparou a operação, mas o MCP não conseguiu registrar "
                    "a correlação de interação. Não tente executar esta operação."
                ),
                "operation_id": result.get("operation_id"),
            }
    return result


@mcp.tool(
    title="Executar reset de dispositivo Akamai MFA",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def reset_akamai_mfa_device(
    operation_id: Annotated[
        str,
        Field(
            description=(
                "operation_id opaco de uma operação Akamai MFA já preparada."
            ),
        ),
    ],
    ctx: Context,
) -> dict[str, Any]:
    """Confirma e executa Akamai MFA somente após interação humana posterior."""
    operation_id = normalize_operation_id(operation_id)
    context, error = _context_or_error(ctx, require_interaction=True)
    if error:
        return error
    return await confirm_then_execute(
        client=client,
        registry=prepared_interactions,
        destructive_execution_enabled=(settings.destructive_execution_mode == "enabled"),
        operation_id=operation_id,
        context=context,
        expected_operation_type="AKAMAI_MFA_DEVICE_RESET",
        expected_domain="akamai_mfa",
    )


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
