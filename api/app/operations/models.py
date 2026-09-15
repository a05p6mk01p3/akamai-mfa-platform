from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Optional


class OperationStatus(StrEnum):
    PREPARED = "PREPARED"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"
    VERIFYING = "VERIFYING"
    REQUIRES_RECONFIRMATION = "REQUIRES_RECONFIRMATION"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    parent_operation_id: Optional[str]
    operation_type: str
    domain: str
    actor_context: Mapping[str, Any]
    session_context: Mapping[str, Any]
    prepared_interaction_ref: Optional[str]
    target_identity: Mapping[str, Any]
    destructive_target: Optional[Mapping[str, Any]]
    prepared_snapshot: Mapping[str, Any]
    status: OperationStatus
    prepared_at: datetime
    confirmed_at: Optional[datetime]
    execution_started_at: Optional[datetime]
    expires_at: datetime
    execution_attempts: int
    post_check_result: Optional[Mapping[str, Any]]
    outcome_code: Optional[str]
    last_error: Optional[Mapping[str, Any]]
    created_at: datetime
    updated_at: datetime
