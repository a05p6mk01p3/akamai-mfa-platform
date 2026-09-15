from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class RequestContext:
    actor_id: str
    session_id: str

    @property
    def actor_context(self) -> dict[str, str]:
        return {"actor": self.actor_id}

    @property
    def session_context(self) -> dict[str, str]:
        return {"session": self.session_id}


@dataclass(frozen=True)
class InteractionContext:
    interaction_ref: str


def require_request_context(
    x_mfa_actor: str | None = Header(default=None, alias="X-MFA-Actor"),
    x_mfa_session: str | None = Header(default=None, alias="X-MFA-Session"),
) -> RequestContext:
    """Internal contextual binding for safe refs.

    This is not the final caller-authentication mechanism. Authentication and
    operator authorization remain a later hardening concern, but references
    already fail closed when contextual correlation is absent.
    """
    actor = (x_mfa_actor or "").strip()
    session = (x_mfa_session or "").strip()
    if not actor or not session:
        raise HTTPException(
            status_code=400,
            detail="X-MFA-Actor and X-MFA-Session are required",
        )
    if len(actor) > 256 or len(session) > 256:
        raise HTTPException(status_code=400, detail="context header too long")
    return RequestContext(actor_id=actor, session_id=session)


def require_interaction_context(
    x_mfa_interaction: str | None = Header(default=None, alias="X-MFA-Interaction"),
) -> InteractionContext:
    """Require an adapter-attested interaction reference.

    The interaction reference is internal transport context. It is not a model
    argument and is never interpreted as human confirmation by itself.
    """
    interaction = (x_mfa_interaction or "").strip()
    if not interaction:
        raise HTTPException(
            status_code=400,
            detail="X-MFA-Interaction is required",
        )
    if len(interaction) > 256:
        raise HTTPException(status_code=400, detail="interaction header too long")
    return InteractionContext(interaction_ref=interaction)
