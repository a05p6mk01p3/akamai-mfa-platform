from __future__ import annotations

import os
import re
from dataclasses import dataclass


_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ALLOWED_ATTESTATION_MODES = {"disabled", "request_header"}
_ALLOWED_DESTRUCTIVE_EXECUTION_MODES = {"disabled", "enabled"}
_ALLOWED_TRUSTED_CONTEXT_MODES = {"static", "request_headers"}
_ALLOWED_TRUSTED_INGRESS_MODES = {"disabled", "shared_secret"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_timeout: float
    mcp_host: str
    mcp_port: int
    log_level: str
    api_actor: str | None
    api_session: str | None
    interaction_attestation_mode: str
    interaction_header_name: str
    log_attestation_probe: bool
    destructive_execution_mode: str
    trusted_context_mode: str = "static"
    actor_header_name: str = "X-MFA-Actor"
    session_header_name: str = "X-MFA-Session"
    trusted_ingress_mode: str = "disabled"
    trusted_ingress_header_name: str = "X-MFA-Ingress-Token"
    trusted_ingress_secret: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        actor = (os.getenv("MCP_API_ACTOR") or "").strip() or None
        session = (os.getenv("MCP_API_SESSION") or "").strip() or None
        mode = (
            os.getenv("MCP_INTERACTION_ATTESTATION_MODE", "disabled")
            .strip()
            .casefold()
        )
        if mode not in _ALLOWED_ATTESTATION_MODES:
            raise ValueError(
                "MCP_INTERACTION_ATTESTATION_MODE must be disabled or request_header"
            )

        header_name = (
            os.getenv("MCP_INTERACTION_HEADER_NAME", "X-MFA-Interaction")
            .strip()
        )
        if not _HEADER_NAME_RE.fullmatch(header_name):
            raise ValueError("MCP_INTERACTION_HEADER_NAME is invalid")

        trusted_context_mode = (
            os.getenv("MCP_TRUSTED_CONTEXT_MODE", "static")
            .strip()
            .casefold()
        )
        if trusted_context_mode not in _ALLOWED_TRUSTED_CONTEXT_MODES:
            raise ValueError(
                "MCP_TRUSTED_CONTEXT_MODE must be static or request_headers"
            )

        actor_header_name = (
            os.getenv("MCP_ACTOR_HEADER_NAME", "X-MFA-Actor").strip()
        )
        session_header_name = (
            os.getenv("MCP_SESSION_HEADER_NAME", "X-MFA-Session").strip()
        )
        for name, value in (
            ("MCP_ACTOR_HEADER_NAME", actor_header_name),
            ("MCP_SESSION_HEADER_NAME", session_header_name),
        ):
            if not _HEADER_NAME_RE.fullmatch(value):
                raise ValueError(f"{name} is invalid")

        trusted_ingress_mode = (
            os.getenv("MCP_TRUSTED_INGRESS_MODE", "disabled")
            .strip()
            .casefold()
        )
        if trusted_ingress_mode not in _ALLOWED_TRUSTED_INGRESS_MODES:
            raise ValueError(
                "MCP_TRUSTED_INGRESS_MODE must be disabled or shared_secret"
            )

        trusted_ingress_header_name = (
            os.getenv(
                "MCP_TRUSTED_INGRESS_HEADER_NAME",
                "X-MFA-Ingress-Token",
            ).strip()
        )
        if not _HEADER_NAME_RE.fullmatch(trusted_ingress_header_name):
            raise ValueError("MCP_TRUSTED_INGRESS_HEADER_NAME is invalid")

        ingress_secret_env = os.getenv("MCP_TRUSTED_INGRESS_SECRET")
        ingress_secret_file = (
            os.getenv("MCP_TRUSTED_INGRESS_SECRET_FILE") or ""
        ).strip() or None
        if ingress_secret_env is not None and ingress_secret_file is not None:
            raise ValueError(
                "configure only one of MCP_TRUSTED_INGRESS_SECRET or "
                "MCP_TRUSTED_INGRESS_SECRET_FILE"
            )
        trusted_ingress_secret: str | None = None
        if ingress_secret_file is not None:
            try:
                with open(
                    ingress_secret_file,
                    "r",
                    encoding="utf-8",
                ) as secret_file:
                    trusted_ingress_secret = secret_file.read().strip()
            except OSError as exc:
                raise ValueError(
                    "MCP_TRUSTED_INGRESS_SECRET_FILE could not be read"
                ) from exc
        elif ingress_secret_env is not None:
            trusted_ingress_secret = ingress_secret_env.strip()

        if trusted_ingress_mode == "shared_secret":
            if not trusted_ingress_secret:
                raise ValueError(
                    "shared_secret ingress requires MCP_TRUSTED_INGRESS_SECRET "
                    "or MCP_TRUSTED_INGRESS_SECRET_FILE"
                )
            if len(trusted_ingress_secret) < 32:
                raise ValueError(
                    "trusted ingress secret must be at least 32 characters"
                )
            if len(trusted_ingress_secret) > 4096 or any(
                ord(ch) < 32 or ord(ch) == 127
                for ch in trusted_ingress_secret
            ):
                raise ValueError("trusted ingress secret is invalid")

        if (
            trusted_context_mode == "request_headers"
            and trusted_ingress_mode != "shared_secret"
        ):
            raise ValueError(
                "MCP_TRUSTED_CONTEXT_MODE=request_headers requires "
                "MCP_TRUSTED_INGRESS_MODE=shared_secret"
            )

        destructive_execution_mode = (
            os.getenv("MCP_DESTRUCTIVE_EXECUTION_MODE", "disabled")
            .strip()
            .casefold()
        )
        if destructive_execution_mode not in _ALLOWED_DESTRUCTIVE_EXECUTION_MODES:
            raise ValueError(
                "MCP_DESTRUCTIVE_EXECUTION_MODE must be disabled or enabled"
            )

        return cls(
            api_url=os.getenv(
                "MFA_API_URL",
                "http://akamai-mfa-api:8000",
            ).rstrip("/"),
            api_timeout=float(os.getenv("MFA_API_TIMEOUT", "20")),
            mcp_host=os.getenv("MCP_HOST", "0.0.0.0"),
            mcp_port=int(os.getenv("MCP_PORT", "9000")),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
            api_actor=actor,
            api_session=session,
            interaction_attestation_mode=mode,
            interaction_header_name=header_name,
            log_attestation_probe=_env_bool(
                "MCP_LOG_ATTESTATION_PROBE",
                False,
            ),
            destructive_execution_mode=destructive_execution_mode,
            trusted_context_mode=trusted_context_mode,
            actor_header_name=actor_header_name,
            session_header_name=session_header_name,
            trusted_ingress_mode=trusted_ingress_mode,
            trusted_ingress_header_name=trusted_ingress_header_name,
            trusted_ingress_secret=trusted_ingress_secret,
        )
