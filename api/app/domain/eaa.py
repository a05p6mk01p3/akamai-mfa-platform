from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class EaaUserRecord:
    """Internal EAA identity. `internal_reset_id` must never cross the API boundary."""

    username: Optional[str]
    samaccountname: Optional[str]
    display_name: Optional[str]
    status: Optional[str]
    login_mfa: Optional[bool]
    internal_reset_id: Optional[str]
    raw: Mapping[str, Any]

    @property
    def exact_identifiers(self) -> Tuple[str, ...]:
        values: list[str] = []
        for value in (self.username, self.samaccountname):
            if value and value.casefold() not in {item.casefold() for item in values}:
                values.append(value)
        return tuple(values)


@dataclass(frozen=True)
class SafeEaaUser:
    username: str
    display_name: Optional[str]
    status: Optional[str]
    eaa_native_mfa_configured: Optional[bool]
    otp_reset_available: bool
