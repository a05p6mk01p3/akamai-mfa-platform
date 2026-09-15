from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any

from .config import Settings


class TrustedContextUnavailable(RuntimeError):
    pass


class TrustedIngressUnavailable(TrustedContextUnavailable):
    pass


_INTERACTION_FINGERPRINT_KEY = secrets.token_bytes(32)


def interaction_fingerprint(
    value: str,
    *,
    key: bytes | None = None,
    length: int = 12,
) -> str:
    """Return a short keyed fingerprint for development observability.

    The key is process-local by default, so fingerprints are only comparable
    within one MCP process lifetime. The raw interaction reference is never
    logged or persisted.
    """
    if not value:
        raise ValueError("interaction reference must be non-empty")
    if length < 8 or length > 64:
        raise ValueError("fingerprint length must be between 8 and 64")
    digest = hmac.new(
        key or _INTERACTION_FINGERPRINT_KEY,
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:length]


@dataclass(frozen=True)
class ApiRequestContext:
    actor: str
    session: str
    interaction_ref: str | None = None
    interaction_source: str | None = None
    actor_source: str | None = None
    session_source: str | None = None

    def headers(self) -> dict[str, str]:
        """Headers safe for read-only API requests.

        Interaction attestation is deliberately NOT forwarded by this method.
        CS02 does not call prepare/confirm/execute/retry endpoints.
        """
        return {
            "X-MFA-Actor": self.actor,
            "X-MFA-Session": self.session,
        }

    def destructive_context_headers(self) -> dict[str, str]:
        """Future API headers for prepare/confirm/execute wiring.

        CS02 defines this boundary but does not use it in any backend method.
        """
        headers = self.headers()
        if self.interaction_ref is None:
            raise TrustedContextUnavailable(
                "interação humana confiável não está disponível"
            )
        headers["X-MFA-Interaction"] = self.interaction_ref
        return headers


def _lookup_header(
    headers: Mapping[str, str] | None,
    name: str,
) -> str | None:
    if headers is None:
        return None
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value)
    return None


def _validate_context_value(value: str, label: str) -> str:
    ref = value.strip()
    if not ref:
        raise TrustedContextUnavailable(f"{label} está vazio")
    if len(ref) > 256:
        raise TrustedContextUnavailable(f"{label} excede o limite permitido")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in ref):
        raise TrustedContextUnavailable(f"{label} contém caracteres inválidos")
    if "{{" in ref or "}}" in ref:
        raise TrustedContextUnavailable(
            f"{label} contém placeholder não resolvido"
        )
    return ref


def _validate_interaction_ref(value: str) -> str:
    return _validate_context_value(value, "referência de interação humana")


class RequestBoundContextProvider:
    """Runtime-owned MCP→API context.

    CS05 supports two actor/session modes:

    * ``static`` keeps the CS01-CS04 deployment-owned development context.
    * ``request_headers`` reads actor/session from transport headers injected by
      the trusted host/runtime. These values are never MCP tool arguments.

    Interaction attestation remains independently request-bound through
    ``MCP_INTERACTION_ATTESTATION_MODE=request_header``. Production use of
    request headers requires an admin-controlled LibreChat configuration and a
    network boundary that prevents untrusted clients from spoofing them.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _validate_trusted_ingress(
        self,
        request_context: Any | None,
    ) -> str | None:
        mode = self.settings.trusted_ingress_mode
        if mode == "disabled":
            return None

        headers = getattr(request_context, "headers", None)
        provided = _lookup_header(
            headers,
            self.settings.trusted_ingress_header_name,
        )
        expected = self.settings.trusted_ingress_secret
        if provided is None or expected is None:
            raise TrustedIngressUnavailable(
                "autenticação do ingress confiável não está disponível"
            )
        provided = provided.strip()
        if (
            not provided
            or len(provided) > 4096
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in provided)
        ):
            raise TrustedIngressUnavailable(
                "autenticação do ingress confiável é inválida"
            )
        if not hmac.compare_digest(provided, expected):
            raise TrustedIngressUnavailable(
                "autenticação do ingress confiável é inválida"
            )
        return "request_header_shared_secret"

    def _actor_session(
        self,
        request_context: Any | None,
    ) -> tuple[str, str, str, str]:
        mode = self.settings.trusted_context_mode
        if mode == "static":
            actor = self.settings.api_actor
            session = self.settings.api_session
            if not actor or not session:
                raise TrustedContextUnavailable(
                    "contexto MCP→API estático indisponível; configure "
                    "MCP_API_ACTOR e MCP_API_SESSION"
                )
            return (
                _validate_context_value(actor, "actor MCP→API"),
                _validate_context_value(session, "session MCP→API"),
                "deployment_static",
                "deployment_static",
            )

        headers = getattr(request_context, "headers", None)
        raw_actor = _lookup_header(headers, self.settings.actor_header_name)
        raw_session = _lookup_header(headers, self.settings.session_header_name)
        if raw_actor is None or raw_session is None:
            raise TrustedContextUnavailable(
                "headers confiáveis de actor/session não estão disponíveis"
            )
        return (
            _validate_context_value(raw_actor, "actor request-bound"),
            _validate_context_value(raw_session, "session request-bound"),
            "request_header",
            "request_header",
        )

    def current(
        self,
        request_context: Any | None = None,
        *,
        require_interaction: bool = False,
    ) -> ApiRequestContext:
        self._validate_trusted_ingress(request_context)
        actor, session, actor_source, session_source = self._actor_session(
            request_context
        )

        interaction_ref: str | None = None
        interaction_source: str | None = None

        mode = self.settings.interaction_attestation_mode
        if mode == "request_header":
            headers = getattr(request_context, "headers", None)
            raw = _lookup_header(
                headers,
                self.settings.interaction_header_name,
            )
            if raw is not None:
                interaction_ref = _validate_interaction_ref(raw)
                interaction_source = "request_header"

        if require_interaction and interaction_ref is None:
            if mode == "disabled":
                raise TrustedContextUnavailable(
                    "attestation de interação humana está desabilitada"
                )
            raise TrustedContextUnavailable(
                "header confiável de interação humana não está disponível"
            )

        return ApiRequestContext(
            actor=actor,
            session=session,
            interaction_ref=interaction_ref,
            interaction_source=interaction_source,
            actor_source=actor_source,
            session_source=session_source,
        )
