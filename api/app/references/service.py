from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..domain.eaa import EaaUserRecord, SafeEaaUser
from ..services.akamai_mfa import AkamaiMfaStatus, ObservedFactor
from .models import ReferenceType, SafeReference
from .repository import SafeReferenceRepository


class UnsafeReferenceRequest(RuntimeError):
    pass


@dataclass(frozen=True)
class ReferencedEaaUser:
    reference: SafeReference
    safe_user: SafeEaaUser


@dataclass(frozen=True)
class ReferencedFactor:
    factor: ObservedFactor
    device_ref: str | None


class SafeReferenceService:
    IDENTITY_DOMAIN = "identity"
    AKAMAI_MFA_DOMAIN = "akamai_mfa"

    def __init__(self, repository: SafeReferenceRepository) -> None:
        self.repository = repository

    def issue_user_ref(
        self,
        record: EaaUserRecord,
        safe_user: SafeEaaUser,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
    ) -> ReferencedEaaUser:
        username = safe_user.username
        reference = self.repository.issue(
            reference_type=ReferenceType.USER,
            domain=self.IDENTITY_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            target_identity={
                "username": username,
                "display_name": safe_user.display_name,
            },
            internal_target={
                "username": username,
                "samaccountname": record.samaccountname,
                "eaa_reset_id": record.internal_reset_id,
            },
        )
        return ReferencedEaaUser(reference=reference, safe_user=safe_user)

    def resolve_user_ref(
        self,
        user_ref: str,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
    ) -> SafeReference:
        return self.repository.resolve(
            user_ref,
            expected_type=ReferenceType.USER,
            expected_domain=self.IDENTITY_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
        )

    def issue_device_ref(
        self,
        factor: ObservedFactor,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        target_identity: Mapping[str, Any],
    ) -> SafeReference:
        if not factor.reset_eligible:
            raise UnsafeReferenceRequest("protected factor cannot receive device_ref")
        if not factor.internal.internal_device_id:
            raise UnsafeReferenceRequest("eligible factor missing internal device id")
        return self.repository.issue(
            reference_type=ReferenceType.DEVICE,
            domain=self.AKAMAI_MFA_DOMAIN,
            actor_context=actor_context,
            session_context=session_context,
            target_identity=target_identity,
            internal_target={"device_id": factor.internal.internal_device_id},
        )

    def reference_status_factors(
        self,
        status: AkamaiMfaStatus,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        target_identity: Mapping[str, Any],
    ) -> tuple[ReferencedFactor, ...]:
        """Issue device_ref only for explicitly eligible observed factors."""
        result: list[ReferencedFactor] = []
        for factor in status.factors:
            device_ref = None
            if factor.reset_eligible:
                ref = self.issue_device_ref(
                    factor,
                    actor_context=actor_context,
                    session_context=session_context,
                    target_identity=target_identity,
                )
                device_ref = ref.reference_id
            result.append(ReferencedFactor(factor=factor, device_ref=device_ref))
        return tuple(result)
