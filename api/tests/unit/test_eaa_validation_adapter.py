import unittest
from types import SimpleNamespace

from app.errors import UpstreamError, UpstreamTimeout
from app.operations.execution import (
    EaaTenantValidationExecutionAdapter,
    PrimitiveDisposition,
    VerificationDisposition,
)


def operation():
    return SimpleNamespace(
        operation_type="EAA_NATIVE_MFA_OTP_RESET",
        destructive_target={"eaa_reset_id": "secret"},
        target_identity={"username": "u1"},
    )


class Service:
    def __init__(self):
        self.reset_calls = 0
        self.reset_effect = 200
        self.observation = SimpleNamespace(
            exact_identity=True,
            username="u1",
            status="1",
            login_mfa=False,
            otp_reset_available=True,
        )

    def reset_otp(self, reset_id):
        self.reset_calls += 1
        if isinstance(self.reset_effect, Exception):
            raise self.reset_effect
        return self.reset_effect

    def observe_otp(self, username):
        return self.observation


class EaaValidationAdapterTests(unittest.TestCase):
    def test_expected_transport_still_never_assumes_success(self):
        service = Service()
        adapter = EaaTenantValidationExecutionAdapter(service)
        primitive = adapter.mutate(operation())
        verification = adapter.verify(operation())

        self.assertEqual(primitive.disposition, PrimitiveDisposition.EXPECTED)
        self.assertEqual(service.reset_calls, 1)
        self.assertEqual(
            verification.disposition,
            VerificationDisposition.INCONCLUSIVE,
        )
        self.assertFalse(verification.safe_details["success_criterion_validated"])
        self.assertFalse(verification.safe_details["akamai_mfa_observed"])

    def test_timeout_is_ambiguous_not_failed(self):
        service = Service()
        service.reset_effect = UpstreamTimeout("timeout")
        adapter = EaaTenantValidationExecutionAdapter(service)

        result = adapter.mutate(operation())

        self.assertEqual(result.disposition, PrimitiveDisposition.AMBIGUOUS)
        self.assertEqual(service.reset_calls, 1)

    def test_5xx_is_ambiguous(self):
        service = Service()
        service.reset_effect = UpstreamError("server", status_code=503)
        adapter = EaaTenantValidationExecutionAdapter(service)
        result = adapter.mutate(operation())
        self.assertEqual(result.disposition, PrimitiveDisposition.AMBIGUOUS)

    def test_4xx_is_conclusive_failure(self):
        service = Service()
        service.reset_effect = UpstreamError("bad", status_code=400)
        adapter = EaaTenantValidationExecutionAdapter(service)
        result = adapter.mutate(operation())
        self.assertEqual(result.disposition, PrimitiveDisposition.FAILED)

    def test_adapter_rejects_akamai_mfa_operation(self):
        service = Service()
        adapter = EaaTenantValidationExecutionAdapter(service)
        other = SimpleNamespace(operation_type="AKAMAI_MFA_DEVICE_RESET")
        self.assertFalse(adapter.supports(other))


if __name__ == "__main__":
    unittest.main()
