import unittest
from types import SimpleNamespace

from app.domain.device_policy import DeviceClassification
from app.errors import UpstreamError, UpstreamTimeout
from app.operations.execution import (
    AkamaiMfaTenantValidationExecutionAdapter,
    PrimitiveDisposition,
    VerificationDisposition,
)


def factor(
    device_id,
    *,
    reset_eligible,
    classification,
    device_type="AKAMAI_AUTHENTICATOR",
    created_by="USER",
    external_source=None,
    platform="android",
):
    return SimpleNamespace(
        type=device_type,
        created_by=created_by,
        external_source=external_source,
        platform=platform,
        classification=classification,
        reset_eligible=reset_eligible,
        internal=SimpleNamespace(internal_device_id=device_id),
    )


TARGET_BASELINE = {
    "device_id": "target",
    "is_target": True,
    "classification": "USER_AUTHENTICATOR",
    "reset_eligible": True,
    "type": "AKAMAI_AUTHENTICATOR",
    "created_by": "USER",
    "external_source": None,
    "platform": "android",
}

PROTECTED_BASELINE = {
    "device_id": "protected",
    "is_target": False,
    "classification": "EXTERNAL_EAA",
    "reset_eligible": False,
    "type": "EMAIL_ADDRESS",
    "created_by": "EXTERNAL",
    "external_source": "eaa",
    "platform": "Email address",
}

OTHER_BASELINE = {
    "device_id": "other",
    "is_target": False,
    "classification": "USER_AUTHENTICATOR",
    "reset_eligible": True,
    "type": "AKAMAI_AUTHENTICATOR",
    "created_by": "USER",
    "external_source": None,
    "platform": "ios",
}


def operation():
    return SimpleNamespace(
        operation_type="AKAMAI_MFA_DEVICE_RESET",
        destructive_target={
            "device_id": "target",
            "postcheck_factor_baseline": [
                TARGET_BASELINE,
                PROTECTED_BASELINE,
                OTHER_BASELINE,
            ],
        },
        target_identity={"username": "u1"},
    )


class Service:
    def __init__(self):
        self.delete_calls = 0
        self.delete_effect = 204
        self.status = SimpleNamespace(
            account_present=True,
            account_status="PROVISIONED",
            factors=(
                factor(
                    "protected",
                    reset_eligible=False,
                    classification=DeviceClassification.EXTERNAL_EAA,
                    device_type="EMAIL_ADDRESS",
                    created_by="EXTERNAL",
                    external_source="eaa",
                    platform="Email address",
                ),
                factor(
                    "other",
                    reset_eligible=True,
                    classification=DeviceClassification.USER_AUTHENTICATOR,
                    platform="ios",
                ),
            ),
        )

    def delete_device(self, device_id):
        self.delete_calls += 1
        if isinstance(self.delete_effect, Exception):
            raise self.delete_effect
        return self.delete_effect

    def status_for_username(self, username):
        if isinstance(self.status, Exception):
            raise self.status
        return self.status


class AkamaiMfaValidationAdapterTests(unittest.TestCase):
    def test_204_then_target_absent_and_others_preserved_is_success_state(self):
        service = Service()
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)

        primitive = adapter.mutate(operation())
        verification = adapter.verify(operation())

        self.assertEqual(primitive.disposition, PrimitiveDisposition.EXPECTED)
        self.assertEqual(service.delete_calls, 1)
        self.assertEqual(
            verification.disposition,
            VerificationDisposition.EXPECTED_STATE,
        )
        self.assertTrue(verification.safe_details["target_absent"])
        self.assertTrue(verification.safe_details["protected_factors_preserved"])
        self.assertTrue(verification.safe_details["non_target_factors_preserved"])

    def test_timeout_is_ambiguous_and_never_retried(self):
        service = Service()
        service.delete_effect = UpstreamTimeout("timeout")
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)

        result = adapter.mutate(operation())

        self.assertEqual(result.disposition, PrimitiveDisposition.AMBIGUOUS)
        self.assertEqual(service.delete_calls, 1)
        self.assertFalse(result.safe_details["automatic_retry_performed"])

    def test_404_is_ambiguous_because_concurrent_removal_is_possible(self):
        service = Service()
        service.delete_effect = UpstreamError("not found", status_code=404)
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)

        result = adapter.mutate(operation())

        self.assertEqual(result.disposition, PrimitiveDisposition.AMBIGUOUS)
        self.assertEqual(service.delete_calls, 1)

    def test_5xx_is_ambiguous(self):
        service = Service()
        service.delete_effect = UpstreamError("server", status_code=503)
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        self.assertEqual(
            adapter.mutate(operation()).disposition,
            PrimitiveDisposition.AMBIGUOUS,
        )

    def test_other_4xx_is_conclusive_failure(self):
        service = Service()
        service.delete_effect = UpstreamError("forbidden", status_code=403)
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        self.assertEqual(
            adapter.mutate(operation()).disposition,
            PrimitiveDisposition.FAILED,
        )

    def test_unexpected_2xx_is_ambiguous(self):
        service = Service()
        service.delete_effect = 200
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        self.assertEqual(
            adapter.mutate(operation()).disposition,
            PrimitiveDisposition.AMBIGUOUS,
        )

    def test_target_remains_is_target_remains(self):
        service = Service()
        service.status = SimpleNamespace(
            account_present=True,
            account_status="ACTIVE",
            factors=service.status.factors
            + (
                factor(
                    "target",
                    reset_eligible=True,
                    classification=DeviceClassification.USER_AUTHENTICATOR,
                ),
            ),
        )
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        result = adapter.verify(operation())
        self.assertEqual(
            result.disposition,
            VerificationDisposition.TARGET_REMAINS,
        )

    def test_account_absent_is_wrong_state(self):
        service = Service()
        service.status = SimpleNamespace(
            account_present=False,
            account_status=None,
            factors=(),
        )
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        result = adapter.verify(operation())
        self.assertEqual(result.disposition, VerificationDisposition.WRONG_STATE)

    def test_protected_factor_loss_is_wrong_state(self):
        service = Service()
        service.status = SimpleNamespace(
            account_present=True,
            account_status="ACTIVE",
            factors=(
                factor(
                    "other",
                    reset_eligible=True,
                    classification=DeviceClassification.USER_AUTHENTICATOR,
                    platform="ios",
                ),
            ),
        )
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        result = adapter.verify(operation())
        self.assertEqual(result.disposition, VerificationDisposition.WRONG_STATE)
        self.assertFalse(result.safe_details["protected_factors_preserved"])

    def test_non_target_eligible_factor_loss_is_wrong_state(self):
        service = Service()
        service.status = SimpleNamespace(
            account_present=True,
            account_status="ACTIVE",
            factors=(
                factor(
                    "protected",
                    reset_eligible=False,
                    classification=DeviceClassification.EXTERNAL_EAA,
                    device_type="EMAIL_ADDRESS",
                    created_by="EXTERNAL",
                    external_source="eaa",
                    platform="Email address",
                ),
            ),
        )
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        result = adapter.verify(operation())
        self.assertEqual(result.disposition, VerificationDisposition.WRONG_STATE)
        self.assertFalse(result.safe_details["non_target_factors_preserved"])

    def test_adapter_rejects_eaa_operation(self):
        service = Service()
        adapter = AkamaiMfaTenantValidationExecutionAdapter(service)
        other = SimpleNamespace(operation_type="EAA_NATIVE_MFA_OTP_RESET")
        self.assertFalse(adapter.supports(other))


if __name__ == "__main__":
    unittest.main()
