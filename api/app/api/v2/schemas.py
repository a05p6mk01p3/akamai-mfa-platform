from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EaaUserCandidateResponse(BaseModel):
    user_ref: str
    username: str
    display_name: str | None = None
    status: str | None = None
    eaa_native_mfa_configured: bool | None = None
    otp_reset_available: bool


class EaaUserSearchResponse(BaseModel):
    status: Literal["found", "ambiguous", "not_found"]
    query: str
    count: int
    total_count: int | None = Field(default=None, ge=0)
    refinement_required: bool = False
    candidates: list[EaaUserCandidateResponse]


class AkamaiMfaFactorResponse(BaseModel):
    type: str | None = None
    created_by: str | None = None
    external_source: str | None = None
    platform: str | None = None
    classification: str
    reset_eligible: bool
    device_ref: str | None = None


class AkamaiMfaStatusResponse(BaseModel):
    user_ref: str
    account_present: bool
    account_status: str | None = None
    business_state: str | None = None
    eligible_factor_count: int = Field(ge=0)
    selection_required: bool
    factors: list[AkamaiMfaFactorResponse]


class EaaOtpPrepareRequest(BaseModel):
    user_ref: str = Field(min_length=8, max_length=128)


class AkamaiDeviceResetPrepareRequest(BaseModel):
    user_ref: str = Field(min_length=8, max_length=128)
    device_ref: str | None = Field(default=None, min_length=8, max_length=128)


class PreparedOperationResponse(BaseModel):
    status: Literal["prepared"] = "prepared"
    confirmation_required: Literal[True] = True
    operation_id: str
    operation_type: str
    domain: str
    target: dict[str, Any]
    expires_at: datetime
    request_id: str | None = None


class RetryAlreadyCompletedResponse(BaseModel):
    status: Literal["already_completed"] = "already_completed"
    confirmation_required: Literal[False] = False
    operation_id: str
    operation_type: str
    domain: str
    target: dict[str, Any]
    outcome_code: str
    request_id: str | None = None


class OperationConfirmationResponse(BaseModel):
    operation_id: str
    operation_type: str
    domain: str
    status: Literal["CONFIRMED"]
    confirmation_accepted: Literal[True] = True
    confirmed_at: datetime
    expires_at: datetime
    request_id: str | None = None


class OperationExecutionResponse(BaseModel):
    operation_id: str
    operation_type: str
    domain: str
    status: str
    outcome_code: str | None = None
    post_check_result: dict[str, Any] | None = None
    simulation: bool
    request_id: str | None = None


class OperationStatusResponse(BaseModel):
    operation_id: str
    operation_type: str
    domain: str
    status: str
    target: dict[str, Any]
    prepared_snapshot: dict[str, Any]
    expires_at: datetime
    outcome_code: str | None = None
    post_check_result: dict[str, Any] | None = None
    request_id: str | None = None


class SafeErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    code: str
    message: str
    request_id: str | None = None
