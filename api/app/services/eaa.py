from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence, Tuple

from ..clients.eaa import EaaClient
from ..domain.eaa import EaaUserRecord, SafeEaaUser


class EaaSearchResultType(str, Enum):
    FOUND = "found"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class EaaCandidate:
    safe: SafeEaaUser
    internal: EaaUserRecord


@dataclass(frozen=True)
class EaaSearchResult:
    result: EaaSearchResultType
    candidates: Tuple[EaaCandidate, ...]
    total_count: int | None = None
    refinement_required: bool = False

    @property
    def users(self) -> Tuple[SafeEaaUser, ...]:
        return tuple(candidate.safe for candidate in self.candidates)

    @property
    def resolved_internal(self) -> EaaUserRecord | None:
        if self.result == EaaSearchResultType.FOUND and len(self.candidates) == 1:
            return self.candidates[0].internal
        return None


class EaaService:
    def __init__(self, client: EaaClient) -> None:
        self.client = client

    @staticmethod
    def _safe(record: EaaUserRecord) -> SafeEaaUser | None:
        username = record.username or record.samaccountname
        if not username:
            return None
        return SafeEaaUser(
            username=username,
            display_name=record.display_name,
            status=record.status,
            eaa_native_mfa_configured=record.login_mfa,
            otp_reset_available=bool(record.internal_reset_id),
        )

    @classmethod
    def _candidate(cls, record: EaaUserRecord) -> EaaCandidate | None:
        safe = cls._safe(record)
        return EaaCandidate(safe=safe, internal=record) if safe is not None else None

    @classmethod
    def resolve(
        cls,
        query: str,
        matches: Sequence[EaaUserRecord],
        *,
        total_count: int | None = None,
        has_more: bool = False,
    ) -> EaaSearchResult:
        target = query.casefold()
        observed_count = len(matches)

        if (
            isinstance(total_count, int)
            and not isinstance(total_count, bool)
            and total_count >= 0
        ):
            known_total: int | None = max(total_count, observed_count)
        else:
            known_total = None

        exact = [
            record
            for record in matches
            if any(
                identifier.casefold() == target
                for identifier in record.exact_identifiers
            )
        ]

        # Exact username/sAMAccountName wins even when the upstream query
        # returned a broader result set.
        if len(exact) == 1:
            candidate = cls._candidate(exact[0])
            if candidate is None:
                return EaaSearchResult(
                    EaaSearchResultType.NOT_FOUND,
                    (),
                    total_count=known_total,
                )
            return EaaSearchResult(
                EaaSearchResultType.FOUND,
                (candidate,),
                total_count=known_total,
                refinement_required=False,
            )

        # A broad name search must never emit actionable safe references.
        # The operator must narrow q using a full name or username.
        if has_more or (known_total is not None and known_total > 5) or observed_count > 5:
            return EaaSearchResult(
                EaaSearchResultType.AMBIGUOUS,
                (),
                total_count=known_total,
                refinement_required=True,
            )

        candidates = tuple(
            candidate
            for candidate in (
                cls._candidate(record)
                for record in matches[:5]
            )
            if candidate is not None
        )

        if not candidates:
            return EaaSearchResult(
                EaaSearchResultType.NOT_FOUND,
                (),
                total_count=known_total,
            )

        return EaaSearchResult(
            EaaSearchResultType.AMBIGUOUS,
            candidates,
            total_count=known_total,
            refinement_required=False,
        )

    def search(self, query: str) -> EaaSearchResult:
        page = self.client.search_users(query)
        return self.resolve(
            query,
            page.users,
            total_count=page.total_count,
            has_more=page.has_more,
        )



@dataclass(frozen=True)
class EaaOtpObservation:
    exact_identity: bool
    username: str | None
    status: str | None
    login_mfa: bool | None
    otp_reset_available: bool | None


def _observe_from_result(result: EaaSearchResult) -> EaaOtpObservation:
    if result.result != EaaSearchResultType.FOUND or len(result.candidates) != 1:
        return EaaOtpObservation(
            exact_identity=False,
            username=None,
            status=None,
            login_mfa=None,
            otp_reset_available=None,
        )
    candidate = result.candidates[0]
    return EaaOtpObservation(
        exact_identity=True,
        username=candidate.safe.username,
        status=candidate.safe.status,
        login_mfa=candidate.safe.eaa_native_mfa_configured,
        otp_reset_available=candidate.safe.otp_reset_available,
    )


def _reset_otp(self: EaaService, internal_reset_id: str) -> int:
    return self.client.reset_login_mfa(internal_reset_id)


def _observe_otp(self: EaaService, username: str) -> EaaOtpObservation:
    return _observe_from_result(self.search(username))


# Kept as service methods while preserving the existing small class layout.
EaaService.reset_otp = _reset_otp
EaaService.observe_otp = _observe_otp
