from __future__ import annotations

from typing import Any


_ALLOWED_CANDIDATE_KEYS = {
    "user_ref",
    "username",
    "display_name",
    "status",
    "eaa_native_mfa_configured",
    "otp_reset_available",
}

_ALLOWED_FACTOR_KEYS = {
    "type",
    "created_by",
    "external_source",
    "platform",
    "classification",
    "reset_eligible",
    "device_ref",
}


def safe_backend_error(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "message": str(exc),
    }
    code = getattr(exc, "code", None)
    request_id = getattr(exc, "request_id", None)
    if code:
        payload["code"] = str(code)
    if request_id:
        payload["request_id"] = str(request_id)
    return payload


def map_search_result(body: dict[str, Any]) -> dict[str, Any]:
    status = body.get("status")
    if status not in {"found", "ambiguous", "not_found"}:
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou um estado de busca não reconhecido.",
        }

    raw_total_count = body.get("total_count")
    if (
        isinstance(raw_total_count, int)
        and not isinstance(raw_total_count, bool)
        and raw_total_count >= 0
    ):
        total_count: int | None = raw_total_count
    else:
        total_count = None

    raw_candidates = body.get("candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    refinement_required = body.get("refinement_required") is True

    # Defense in depth: an ambiguous backend response that exposes evidence
    # of more than five matches must require a narrower query even if the
    # explicit flag regresses.
    if status == "ambiguous":
        if total_count is not None and total_count > 5:
            refinement_required = True
        if len(raw_candidates) > 5:
            refinement_required = True

    # found/not_found combined with refinement_required is contradictory.
    if refinement_required and status != "ambiguous":
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": (
                "A API retornou refinement_required em um estado "
                "incompatível."
            ),
        }

    candidates: list[dict[str, Any]] = []

    if not refinement_required:
        for item in raw_candidates[:5]:
            if not isinstance(item, dict):
                continue
            candidates.append(
                {
                    key: item.get(key)
                    for key in _ALLOWED_CANDIDATE_KEYS
                    if key in item
                }
            )

    result: dict[str, Any] = {
        "status": status,
        "query": body.get("query"),
        "count": len(candidates),
        "total_count": total_count,
        "refinement_required": refinement_required,
        "candidates": candidates,
    }

    if status == "found":
        result["message"] = (
            "Identidade EAA localizada de forma inequívoca."
        )
    elif status == "ambiguous" and refinement_required:
        result["message"] = (
            "A busca retornou mais resultados do que o limite seguro "
            "de 5 usuários. Informe o nome completo ou o username "
            "para restringir a consulta."
        )
    elif status == "ambiguous":
        result["message"] = (
            "A busca retornou múltiplas identidades seguras; "
            "selecione explicitamente a identidade correta antes "
            "de qualquer preparação destrutiva."
        )
    else:
        result["message"] = (
            "Usuário não encontrado no Akamai EAA."
        )

    return result


def map_akamai_status(body: dict[str, Any]) -> dict[str, Any]:
    raw_factors = body.get("factors")
    if not isinstance(raw_factors, list):
        raw_factors = []

    factors: list[dict[str, Any]] = []
    for item in raw_factors:
        if not isinstance(item, dict):
            continue
        factor = {key: item.get(key) for key in _ALLOWED_FACTOR_KEYS if key in item}
        # Fail closed against a backend regression: protected/non-eligible
        # factors must never carry an actionable device_ref into MCP output.
        if factor.get("reset_eligible") is not True:
            factor["device_ref"] = None
        factors.append(factor)

    eligible_count = body.get("eligible_factor_count")
    if not isinstance(eligible_count, int) or eligible_count < 0:
        eligible_count = sum(1 for factor in factors if factor.get("reset_eligible") is True)

    selection_required = body.get("selection_required")
    if not isinstance(selection_required, bool):
        selection_required = eligible_count > 1

    result = {
        "user_ref": body.get("user_ref"),
        "account_present": bool(body.get("account_present")),
        "account_status": body.get("account_status"),
        "business_state": body.get("business_state"),
        "eligible_factor_count": eligible_count,
        "selection_required": selection_required,
        "factors": factors,
    }

    if not result["account_present"]:
        result["message"] = "Não há conta Akamai MFA para esta identidade."
    elif result["business_state"] == "already_awaiting_enrollment":
        result["message"] = (
            "A conta já está aguardando enrollment; nenhum Akamai Authenticator elegível "
            "foi encontrado para reset."
        )
    elif selection_required:
        result["message"] = (
            "Há múltiplos Akamai Authenticators elegíveis; uma seleção explícita por "
            "device_ref seguro será necessária antes do prepare."
        )
    elif eligible_count == 1:
        result["message"] = (
            "Há um Akamai Authenticator elegível. Fatores externos protegidos não são alvo."
        )
    else:
        result["message"] = "Nenhum Akamai Authenticator elegível foi encontrado."
    return result


def cs02_disabled_tool(tool_name: str) -> dict[str, Any]:
    return {
        "status": "not_available",
        "code": "not_available_in_cs02",
        "tool": tool_name,
        "message": (
            "A attestation de interação do MCP CS02 foi aceita, mas este tool "
            "permanece fail-closed. Nenhuma chamada de prepare, confirm, execute "
            "ou retry foi feita pela API."
        ),
    }


_ALLOWED_PREPARED_TARGET_KEYS = {
    "user_ref",
    "username",
    "display_name",
}

_ALLOWED_OPERATION_TYPES = {
    "EAA_NATIVE_MFA_OTP_RESET",
    "AKAMAI_MFA_DEVICE_RESET",
}

_ALLOWED_DOMAINS = {
    "eaa_native_mfa",
    "akamai_mfa",
}


def map_prepare_result(body: dict[str, Any]) -> dict[str, Any]:
    status = body.get("status")
    if status not in {"prepared", "already_completed"}:
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou um estado de prepare não reconhecido.",
        }

    operation_id = body.get("operation_id")
    operation_type = body.get("operation_type")
    domain = body.get("domain")
    raw_target = body.get("target")

    if (
        not isinstance(operation_id, str)
        or not operation_id.startswith("op_")
        or operation_type not in _ALLOWED_OPERATION_TYPES
        or domain not in _ALLOWED_DOMAINS
        or not isinstance(raw_target, dict)
    ):
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou um contrato de operação inválido.",
        }

    target = {
        key: raw_target.get(key)
        for key in _ALLOWED_PREPARED_TARGET_KEYS
        if key in raw_target
    }

    result: dict[str, Any] = {
        "status": status,
        "confirmation_required": bool(body.get("confirmation_required")),
        "operation_id": operation_id,
        "operation_type": operation_type,
        "domain": domain,
        "target": target,
    }

    request_id = body.get("request_id")
    if isinstance(request_id, str) and request_id:
        result["request_id"] = request_id

    if status == "prepared":
        expires_at = body.get("expires_at")
        if not isinstance(expires_at, str) or not expires_at:
            return {
                "status": "error",
                "code": "unexpected_api_contract",
                "message": "A API não retornou expiração válida para a operação preparada.",
            }
        if body.get("confirmation_required") is not True:
            return {
                "status": "error",
                "code": "unexpected_api_contract",
                "message": "A operação preparada não exige confirmação conforme o contrato.",
            }
        result["confirmation_required"] = True
        result["expires_at"] = expires_at
        result["message"] = (
            "Operação preparada sem executar mutação. "
            "Uma interação humana posterior será necessária antes da execução."
        )
        return result

    # Retry can observe that the effect is already present and create no child.
    outcome_code = body.get("outcome_code")
    if not isinstance(outcome_code, str) or not outcome_code:
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API não retornou outcome válido para retry já concluído.",
        }
    if body.get("confirmation_required") is not False:
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "Retry já concluído retornou contrato de confirmação inválido.",
        }
    result["confirmation_required"] = False
    result["outcome_code"] = outcome_code
    result["message"] = (
        "O efeito esperado já está presente; nenhuma nova operação destrutiva foi preparada."
    )
    return result


def cs03_reset_disabled_tool(tool_name: str) -> dict[str, Any]:
    return {
        "status": "not_available",
        "code": "reset_not_available_in_cs03",
        "tool": tool_name,
        "message": (
            "O MCP CS03 permite apenas prepare. Confirm e execute permanecem "
            "bloqueados; nenhuma mutação foi solicitada à API."
        ),
    }


_ALLOWED_OPERATION_STATES = {
    "PREPARED",
    "CONFIRMED",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED",
    "AMBIGUOUS",
    "VERIFYING",
    "REQUIRES_RECONFIRMATION",
    "EXPIRED",
    "CANCELLED",
}


def map_confirmation_result(
    body: dict[str, Any],
    *,
    operation_id: str,
    expected_operation_type: str,
    expected_domain: str,
) -> dict[str, Any]:
    if (
        body.get("operation_id") != operation_id
        or body.get("operation_type") != expected_operation_type
        or body.get("domain") != expected_domain
        or body.get("status") != "CONFIRMED"
        or body.get("confirmation_accepted") is not True
    ):
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou confirmação incompatível com a operação esperada.",
        }
    confirmed_at = body.get("confirmed_at")
    expires_at = body.get("expires_at")
    if not isinstance(confirmed_at, str) or not isinstance(expires_at, str):
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou metadados inválidos de confirmação.",
        }
    return {
        "status": "CONFIRMED",
        "confirmation_accepted": True,
        "operation_id": operation_id,
        "operation_type": expected_operation_type,
        "domain": expected_domain,
        "confirmed_at": confirmed_at,
        "expires_at": expires_at,
    }


def map_execution_result(
    body: dict[str, Any],
    *,
    operation_id: str,
    expected_operation_type: str,
    expected_domain: str,
) -> dict[str, Any]:
    state = body.get("status")
    if (
        body.get("operation_id") != operation_id
        or body.get("operation_type") != expected_operation_type
        or body.get("domain") != expected_domain
        or state not in _ALLOWED_OPERATION_STATES
        or not isinstance(body.get("simulation"), bool)
    ):
        return {
            "status": "error",
            "code": "unexpected_api_contract",
            "message": "A API retornou resultado de execução incompatível.",
        }

    result: dict[str, Any] = {
        "status": state,
        "operation_id": operation_id,
        "operation_type": expected_operation_type,
        "domain": expected_domain,
        "simulation": body["simulation"],
        "automatic_destructive_retry_performed": False,
    }
    outcome_code = body.get("outcome_code")
    if isinstance(outcome_code, str) and outcome_code:
        result["outcome_code"] = outcome_code
    request_id = body.get("request_id")
    if isinstance(request_id, str) and request_id:
        result["request_id"] = request_id

    if state == "SUCCEEDED":
        result["message"] = "A API concluiu a operação e o post-check requerido reportou sucesso."
    elif state == "REQUIRES_RECONFIRMATION":
        result["message"] = (
            "A autorização anterior foi consumida. Um novo attempt exige pedido humano "
            "explícito e novo child prepare; nenhum retry destrutivo foi feito."
        )
    elif state in {"VERIFYING", "AMBIGUOUS", "EXECUTING"}:
        result["message"] = (
            "O resultado ainda não é conclusivo. Não repita execute; a API deve ser "
            "observada/verificada sem retry destrutivo."
        )
    elif state == "FAILED":
        result["message"] = "A operação terminou sem sucesso; nenhum target alternativo foi usado."
    else:
        result["message"] = "Estado autoritativo retornado pela API."
    return result


def map_operation_observation(
    body: dict[str, Any],
    *,
    operation_id: str,
    expected_operation_type: str,
    expected_domain: str,
) -> dict[str, Any]:
    state = body.get("status")
    if (
        body.get("operation_id") != operation_id
        or body.get("operation_type") != expected_operation_type
        or body.get("domain") != expected_domain
        or state not in _ALLOWED_OPERATION_STATES
    ):
        return {
            "status": "unknown",
            "code": "operation_observation_unavailable",
            "operation_id": operation_id,
            "message": "Não foi possível validar o estado da operação de forma segura.",
        }
    result = {
        "status": state,
        "operation_id": operation_id,
        "operation_type": expected_operation_type,
        "domain": expected_domain,
        "automatic_destructive_retry_performed": False,
    }
    outcome_code = body.get("outcome_code")
    if isinstance(outcome_code, str) and outcome_code:
        result["outcome_code"] = outcome_code
    return result
