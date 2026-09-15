from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from .base import EdgeGridHttpClient
from ..domain.akamai_mfa import AkamaiMfaAccountRecord, AkamaiMfaFactorRecord


class AkamaiMfaClient(EdgeGridHttpClient):
    AMFA_USERS_PATH = "/amfa/v1/users"
    AMFA_DEVICE_PATH = "/amfa/v1/devices/{device_id}"

    @classmethod
    def parse_factor(cls, item: Dict[str, Any]) -> AkamaiMfaFactorRecord:
        return AkamaiMfaFactorRecord(
            device_type=cls.first(item, ("deviceType", "type")),
            created_by=cls.first(item, ("createdBy", "created_by")),
            external_tag=cls.first(item, ("externalTag", "external_tag")),
            platform=cls.first(item, ("platform", "devicePlatform", "os")),
            internal_device_id=cls.first(item, ("deviceId", "id", "device_id")),
            raw=item,
        )

    @classmethod
    def _factor_items(cls, item: Dict[str, Any]) -> Tuple[AkamaiMfaFactorRecord, ...]:
        # Tenant/API revisions may call them devices or factors; both are observation-only here.
        raw_items: List[Dict[str, Any]] = []
        for key in ("devices", "factors"):
            value = item.get(key)
            if isinstance(value, list):
                raw_items.extend(entry for entry in value if isinstance(entry, dict))
        return tuple(cls.parse_factor(entry) for entry in raw_items)

    @classmethod
    def parse_account(cls, item: Dict[str, Any]) -> AkamaiMfaAccountRecord:
        return AkamaiMfaAccountRecord(
            username=cls.first(item, ("username", "userName")),
            account_status=cls.first(item, ("userStatus", "accountStatus", "status")),
            internal_user_id=cls.first(item, ("userId", "user_id")),
            factors=cls._factor_items(item),
            raw=item,
        )

    def search_accounts(self, username: str) -> List[AkamaiMfaAccountRecord]:
        response = self.request(
            "GET",
            self.AMFA_USERS_PATH,
            params={
                "username": username,
                "contractId": self.settings.contract_id,
                # v2 must observe real factors; deviceCount alone is not authority.
                "includeDevices": "true",
            },
        )
        payload = self.safe_json(response)
        return [self.parse_account(item) for item in self.objects(payload)]


    def delete_device(self, internal_device_id: str) -> int:
        """Delete exactly one backend-bound Akamai MFA device.

        No retry is implemented. The caller must treat transport ambiguity
        conservatively and inspect current device state before any retry decision.
        """
        path = self.AMFA_DEVICE_PATH.format(
            device_id=quote(internal_device_id, safe="")
        )
        response = self.request(
            "DELETE",
            path,
            params={"contractId": self.settings.contract_id},
        )
        return response.status_code
