from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .akamai_mfa import AkamaiMfaFactorRecord


class DeviceClassification(str, Enum):
    USER_AUTHENTICATOR = "USER_AUTHENTICATOR"
    EXTERNAL_EAA = "EXTERNAL_EAA"
    OTHER_EXTERNAL = "OTHER_EXTERNAL"
    ADMIN_SYSTEM = "ADMIN_SYSTEM"
    UNKNOWN_PROTECTED = "UNKNOWN_PROTECTED"


@dataclass(frozen=True)
class DeviceDecision:
    classification: DeviceClassification
    reset_eligible: bool


def classify_device(device: AkamaiMfaFactorRecord) -> DeviceDecision:
    """Pure deny-by-default policy frozen by G1/G2."""

    created_by = (device.created_by or "").strip().upper()
    device_type = (device.device_type or "").strip().upper()
    external_tag = (device.external_tag or "").strip().casefold()

    if created_by == "USER" and device_type == "AKAMAI_AUTHENTICATOR":
        return DeviceDecision(DeviceClassification.USER_AUTHENTICATOR, True)

    if created_by == "EXTERNAL" and external_tag == "eaa":
        return DeviceDecision(DeviceClassification.EXTERNAL_EAA, False)

    if created_by == "EXTERNAL":
        return DeviceDecision(DeviceClassification.OTHER_EXTERNAL, False)

    # Treat known non-USER producers as protected admin/system material.
    if created_by and created_by != "USER":
        return DeviceDecision(DeviceClassification.ADMIN_SYSTEM, False)

    return DeviceDecision(DeviceClassification.UNKNOWN_PROTECTED, False)
