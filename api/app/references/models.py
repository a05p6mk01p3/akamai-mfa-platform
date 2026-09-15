from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class ReferenceType(StrEnum):
    USER = "USER"
    DEVICE = "DEVICE"


@dataclass(frozen=True)
class SafeReference:
    reference_id: str
    reference_type: ReferenceType
    domain: str
    actor_context: Mapping[str, Any]
    session_context: Mapping[str, Any]
    target_identity: Mapping[str, Any]
    internal_target: Mapping[str, Any]
    created_at: datetime
    expires_at: datetime
