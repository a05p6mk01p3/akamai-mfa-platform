import unittest
from unittest.mock import AsyncMock, patch

from app.context import ApiRequestContext


class Cs04LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def context(self, interaction="turn-2"):
        return ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref=interaction,
            interaction_source="request_header",
        )

    async def test_same_interaction_blocks_before_api(self):
        from app.lifecycle import confirm_then_execute
        from app.attestation import PreparedInteractionRegistry

        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context("turn-1"),
            expires_at="2099-01-01T00:00:00+00:00",
        )
        fake_client = AsyncMock()
        result = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=False,
            operation_id=op, context=self.context("turn-1"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["code"], "later_human_confirmation_required")
        fake_client.confirm_operation.assert_not_awaited()
        fake_client.execute_operation.assert_not_awaited()

    async def test_disabled_mode_blocks_after_later_interaction(self):
        from app.lifecycle import confirm_then_execute
        from app.attestation import PreparedInteractionRegistry

        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context("turn-1"),
            expires_at="2099-01-01T00:00:00+00:00",
        )
        fake_client = AsyncMock()
        result = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=False,
            operation_id=op, context=self.context("turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["code"], "destructive_execution_disabled_in_cs04")
        fake_client.confirm_operation.assert_not_awaited()
        fake_client.execute_operation.assert_not_awaited()

    async def test_confirm_success_then_execute_once(self):
        from app.lifecycle import confirm_then_execute
        from app.attestation import PreparedInteractionRegistry

        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context("turn-1"),
            expires_at="2099-01-01T00:00:00+00:00",
        )
        fake_client = AsyncMock()
        fake_client.confirm_operation.return_value = {
            "operation_id": op,
            "operation_type": "EAA_NATIVE_MFA_OTP_RESET",
            "domain": "eaa_native_mfa",
            "status": "CONFIRMED",
            "confirmation_accepted": True,
            "confirmed_at": "2026-09-14T15:00:00+00:00",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        fake_client.execute_operation.return_value = {
            "operation_id": op,
            "operation_type": "EAA_NATIVE_MFA_OTP_RESET",
            "domain": "eaa_native_mfa",
            "status": "VERIFYING",
            "outcome_code": "EAA_POSTCHECK_TENANT_VALIDATION_REQUIRED",
            "post_check_result": {"internal": "not-exposed"},
            "simulation": False,
        }
        result = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=True,
            operation_id=op, context=self.context("turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        replay = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=True,
            operation_id=op, context=self.context("turn-3"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["status"], "VERIFYING")
        self.assertNotIn("post_check_result", result)
        self.assertEqual(replay["code"], "operation_locally_consumed")
        fake_client.confirm_operation.assert_awaited_once()
        fake_client.execute_operation.assert_awaited_once()

    async def test_confirm_error_prevents_execute(self):
        from app.lifecycle import confirm_then_execute
        from app.attestation import PreparedInteractionRegistry
        from app.backend import BackendError

        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context("turn-1"),
            expires_at="2099-01-01T00:00:00+00:00",
        )
        fake_client = AsyncMock()
        fake_client.confirm_operation.side_effect = BackendError(
            "expired", status_code=409, code="operation_expired"
        )
        result = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=True,
            operation_id=op, context=self.context("turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["code"], "operation_expired")
        fake_client.execute_operation.assert_not_awaited()

    async def test_execute_timeout_observes_state_without_retry(self):
        from app.lifecycle import confirm_then_execute
        from app.attestation import PreparedInteractionRegistry
        from app.backend import BackendError

        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context("turn-1"),
            expires_at="2099-01-01T00:00:00+00:00",
        )
        fake_client = AsyncMock()
        fake_client.confirm_operation.return_value = {
            "operation_id": op,
            "operation_type": "EAA_NATIVE_MFA_OTP_RESET",
            "domain": "eaa_native_mfa",
            "status": "CONFIRMED",
            "confirmation_accepted": True,
            "confirmed_at": "2026-09-14T15:00:00+00:00",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        fake_client.execute_operation.side_effect = BackendError(
            "timeout", code="backend_timeout"
        )
        fake_client.get_operation_status.return_value = {
            "operation_id": op,
            "operation_type": "EAA_NATIVE_MFA_OTP_RESET",
            "domain": "eaa_native_mfa",
            "status": "VERIFYING",
            "outcome_code": "EAA_POSTCHECK_TENANT_VALIDATION_REQUIRED",
        }
        result = await confirm_then_execute(
            client=fake_client, registry=registry, destructive_execution_enabled=True,
            operation_id=op, context=self.context("turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET", expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["status"], "VERIFYING")
        self.assertEqual(result["code"], "execution_transport_observed")
        fake_client.execute_operation.assert_awaited_once()
        fake_client.get_operation_status.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
