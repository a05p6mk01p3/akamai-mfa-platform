import unittest
from types import SimpleNamespace

from app.operations.execution import (
    ExecutionBackendDisabled,
    PrimitiveDisposition,
)
from app.operations.live import LiveExecutionAdapter


class FakeEaaService:
    def __init__(self):
        self.reset_calls = []

    def reset_otp(self, reset_id):
        self.reset_calls.append(reset_id)
        return 200


class FakeAkamaiMfaService:
    def __init__(self):
        self.delete_calls = []

    def delete_device(self, device_id):
        self.delete_calls.append(device_id)
        return 204


def operation(operation_type, destructive_target):
    return SimpleNamespace(
        operation_type=operation_type,
        destructive_target=destructive_target,
        target_identity={"username": "u1"},
    )


class LiveExecutionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.eaa = FakeEaaService()
        self.amfa = FakeAkamaiMfaService()
        self.adapter = LiveExecutionAdapter(
            eaa_service=self.eaa,
            akamai_mfa_service=self.amfa,
        )

    def test_eaa_operation_dispatches_only_to_eaa_adapter(self):
        op = operation(
            "EAA_NATIVE_MFA_OTP_RESET",
            {"eaa_reset_id": "eaa-target"},
        )

        result = self.adapter.mutate(op)

        self.assertEqual(result.disposition, PrimitiveDisposition.EXPECTED)
        self.assertEqual(self.eaa.reset_calls, ["eaa-target"])
        self.assertEqual(self.amfa.delete_calls, [])

    def test_akamai_mfa_operation_dispatches_only_to_akamai_adapter(self):
        op = operation(
            "AKAMAI_MFA_DEVICE_RESET",
            {"device_id": "device-target"},
        )

        result = self.adapter.mutate(op)

        self.assertEqual(result.disposition, PrimitiveDisposition.EXPECTED)
        self.assertEqual(self.eaa.reset_calls, [])
        self.assertEqual(self.amfa.delete_calls, ["device-target"])

    def test_cross_domain_target_shape_does_not_cross_dispatch(self):
        op = operation(
            "EAA_NATIVE_MFA_OTP_RESET",
            {"device_id": "must-not-be-deleted"},
        )

        result = self.adapter.mutate(op)

        self.assertEqual(result.disposition, PrimitiveDisposition.FAILED)
        self.assertEqual(result.safe_code, "EAA_RESET_TARGET_MISSING")
        self.assertEqual(self.eaa.reset_calls, [])
        self.assertEqual(self.amfa.delete_calls, [])

    def test_unknown_operation_type_is_fail_closed(self):
        op = operation("UNKNOWN_DESTRUCTIVE_OPERATION", {})

        self.assertFalse(self.adapter.supports(op))
        with self.assertRaises(ExecutionBackendDisabled):
            self.adapter.mutate(op)
        self.assertEqual(self.eaa.reset_calls, [])
        self.assertEqual(self.amfa.delete_calls, [])


if __name__ == "__main__":
    unittest.main()
