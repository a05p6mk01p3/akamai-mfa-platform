from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class AkamaiMfaFactorRecord:
    """Internal observed factor/device. `internal_device_id` is never public."""

    device_type: Optional[str]
    created_by: Optional[str]
    external_tag: Optional[str]
    platform: Optional[str]
    internal_device_id: Optional[str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class AkamaiMfaAccountRecord:
    username: Optional[str]
    account_status: Optional[str]
    internal_user_id: Optional[str]
    factors: Tuple[AkamaiMfaFactorRecord, ...]
    raw: Mapping[str, Any]
