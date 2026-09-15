from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import quote

from .base import EdgeGridHttpClient
from ..domain.eaa import EaaUserRecord


@dataclass(frozen=True)
class EaaUserSearchPage:
    users: tuple[EaaUserRecord, ...]
    total_count: int | None
    has_more: bool


class EaaClient(EdgeGridHttpClient):
    USERS_PATH = "/crux/v1/mgmt-pop/directories/{directory_id}/users"
    RESET_MFA_PATH = "/crux/v1/mgmt-pop/tenant/mfa/reset"

    @classmethod
    def parse_user(cls, item: Dict[str, Any]) -> EaaUserRecord:
        normalized = item.get("normalized_attributes")
        if not isinstance(normalized, dict):
            normalized = {}

        username = cls.first(item, ("username", "user_name", "userName", "login", "name"))
        if not username:
            username = cls.first(normalized, ("eaa.userName", "user.userPrincipleName"))

        samaccountname = cls.first(item, ("samaccountname", "samAccountName"))
        if not samaccountname:
            samaccountname = cls.first(normalized, ("user.samAccountName",))

        display_name = cls.first(item, ("display_name", "displayName", "full_name", "fullName"))
        if not display_name:
            first_name = cls.first(item, ("first_name", "firstName")) or ""
            last_name = cls.first(item, ("last_name", "lastName")) or ""
            display_name = f"{first_name} {last_name}".strip() or None

        mfa = item.get("mfa")
        login_mfa = None
        if isinstance(mfa, dict) and isinstance(mfa.get("login_mfa"), bool):
            login_mfa = mfa["login_mfa"]

        return EaaUserRecord(
            username=username,
            samaccountname=samaccountname,
            display_name=display_name,
            status=cls.first(item, ("status", "userStatus")),
            login_mfa=login_mfa,
            internal_reset_id=cls.first(item, ("uuid_url", "uuidUrl")),
            raw=item,
        )

    @classmethod
    def parse_search_page(cls, payload: Any) -> EaaUserSearchPage:
        items = cls.objects(payload)
        users = tuple(cls.parse_user(item) for item in items)

        total_count: int | None = None
        has_more = False

        if isinstance(payload, dict):
            meta = payload.get("meta")
            if isinstance(meta, dict):
                raw_total = meta.get("total_count")
                if raw_total is None:
                    raw_total = meta.get("totalCount")

                if (
                    isinstance(raw_total, int)
                    and not isinstance(raw_total, bool)
                    and raw_total >= 0
                ):
                    total_count = raw_total

                if meta.get("next"):
                    has_more = True

                if meta.get("has_more") is True:
                    has_more = True

            if total_count is None:
                raw_total = payload.get("total_count")
                if raw_total is None:
                    raw_total = payload.get("totalCount")

                if (
                    isinstance(raw_total, int)
                    and not isinstance(raw_total, bool)
                    and raw_total >= 0
                ):
                    total_count = raw_total

        if total_count is not None and total_count > len(users):
            has_more = True

        return EaaUserSearchPage(
            users=users,
            total_count=total_count,
            has_more=has_more,
        )

    def search_users(self, query: str) -> EaaUserSearchPage:
        path = self.USERS_PATH.format(
            directory_id=quote(self.settings.directory_id, safe="")
        )
        response = self.request(
            "GET",
            path,
            params={
                "did": self.settings.directory_id,
                "q": query,
                "contractId": self.settings.contract_id,
            },
        )
        payload = self.safe_json(response)
        return self.parse_search_page(payload)


    def reset_login_mfa(self, internal_reset_id: str) -> int:
        """Issue the tenant-validated EAA Native MFA OTP reset primitive exactly once.

        No retry is implemented here. A transport failure may occur after the
        upstream accepted the mutation, so callers must classify timeout/network/5xx
        conservatively and perform an observational post-check.
        """
        response = self.request(
            "POST",
            self.RESET_MFA_PATH,
            params={"contractId": self.settings.contract_id},
            json={
                "otp_type": "login_mfa",
                "user_id": internal_reset_id,
            },
        )
        return response.status_code
