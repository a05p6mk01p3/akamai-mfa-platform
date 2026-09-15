from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..clients.akamai_mfa import AkamaiMfaClient
from ..domain.akamai_mfa import AkamaiMfaAccountRecord, AkamaiMfaFactorRecord
from ..domain.device_policy import DeviceClassification, classify_device


@dataclass(frozen=True)
class ObservedFactor:
    type: Optional[str]
    created_by: Optional[str]
    external_source: Optional[str]
    platform: Optional[str]
    classification: DeviceClassification
    reset_eligible: bool
    internal: AkamaiMfaFactorRecord


@dataclass(frozen=True)
class AkamaiMfaStatus:
    account_present: bool
    account_status: Optional[str]
    business_state: Optional[str]
    factors: Tuple[ObservedFactor, ...]
    internal_account: AkamaiMfaAccountRecord | None


class AkamaiMfaService:
    def __init__(self, client: AkamaiMfaClient) -> None:
        self.client = client

    @staticmethod
    def _select_exact(username: str, matches: Sequence[AkamaiMfaAccountRecord]) -> AkamaiMfaAccountRecord | None:
        target = username.casefold()
        exact = [m for m in matches if m.username and m.username.casefold() == target]
        if len(exact) == 1:
            return exact[0]
        if not matches:
            return None
        if len(exact) > 1 or len(matches) > 1:
            raise ValueError("ambiguous_akamai_mfa_account")
        raise ValueError("akamai_mfa_account_not_exact")

    @staticmethod
    def inspect_account(account: AkamaiMfaAccountRecord | None) -> AkamaiMfaStatus:
        if account is None:
            return AkamaiMfaStatus(False, None, None, (), None)

        observed: list[ObservedFactor] = []
        eligible_count = 0
        protected_external_count = 0
        for factor in account.factors:
            decision = classify_device(factor)
            if decision.reset_eligible:
                eligible_count += 1
            if decision.classification in {
                DeviceClassification.EXTERNAL_EAA,
                DeviceClassification.OTHER_EXTERNAL,
            }:
                protected_external_count += 1
            observed.append(
                ObservedFactor(
                    type=factor.device_type,
                    created_by=factor.created_by,
                    external_source=factor.external_tag,
                    platform=factor.platform,
                    classification=decision.classification,
                    reset_eligible=decision.reset_eligible,
                    internal=factor,
                )
            )

        business_state = None
        if (
            (account.account_status or "").upper() == "PROVISIONED"
            and eligible_count == 0
            and protected_external_count == len(observed)
            and len(observed) > 0
        ):
            business_state = "already_awaiting_enrollment"

        return AkamaiMfaStatus(
            account_present=True,
            account_status=account.account_status,
            business_state=business_state,
            factors=tuple(observed),
            internal_account=account,
        )

    def status_for_username(self, username: str) -> AkamaiMfaStatus:
        account = self._select_exact(username, self.client.search_accounts(username))
        return self.inspect_account(account)



def _delete_device(self: AkamaiMfaService, internal_device_id: str) -> int:
    return self.client.delete_device(internal_device_id)


AkamaiMfaService.delete_device = _delete_device
