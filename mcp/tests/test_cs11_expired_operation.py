import unittest
from unittest.mock import AsyncMock

from app.attestation import (
    PreparedInteractionExpired,
    PreparedInteractionRegistry,
    PreparedInteractionUnknown,
)
from app.context import ApiRequestContext
from app.lifecycle import confirm_then_execute


OPERATION_TYPE = "AKAMAI_MFA_DEVICE_RESET"
DOMAIN = "akamai_mfa"


class Cs11ExpiredOperationRegistryTests(unittest.TestCase):
    def context(self, interaction="turn-2"):
        return ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref=interaction,
            interaction_source="request_header",
        )

    def record_expired(self, registry, operation_id):
        registry.record(
            operation_id=operation_id,
            operation_type=OPERATION_TYPE,
            domain=DOMAIN,
            context=self.context("turn-1"),
            expires_at="2000-01-01T00:00:00+00:00",
        )

    def test_expired_operation_has_specific_error(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "e" * 20

        self.record_expired(registry, op)

        with self.assertRaises(PreparedInteractionExpired):
            registry.require_later_interaction(
                operation_id=op,
                context=self.context("turn-2"),
                expected_operation_type=OPERATION_TYPE,
                expected_domain=DOMAIN,
            )

    def test_expired_diagnostic_survives_prior_purge(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "f" * 20

        self.record_expired(registry, op)

        self.assertEqual(registry.count(), 0)

        with self.assertRaises(PreparedInteractionExpired):
            registry.claim_for_reset(
                operation_id=op,
                context=self.context("turn-2"),
                expected_operation_type=OPERATION_TYPE,
                expected_domain=DOMAIN,
            )

    def test_expired_tombstones_are_bounded(self):
        registry = PreparedInteractionRegistry(max_entries=1)

        op1 = "op_" + "1" * 20
        op2 = "op_" + "2" * 20

        self.record_expired(registry, op1)
        self.assertEqual(registry.count(), 0)

        self.record_expired(registry, op2)
        self.assertEqual(registry.count(), 0)

        with self.assertRaises(PreparedInteractionUnknown):
            registry.require_later_interaction(
                operation_id=op1,
                context=self.context("turn-2"),
                expected_operation_type=OPERATION_TYPE,
                expected_domain=DOMAIN,
            )

        with self.assertRaises(PreparedInteractionExpired):
            registry.require_later_interaction(
                operation_id=op2,
                context=self.context("turn-2"),
                expected_operation_type=OPERATION_TYPE,
                expected_domain=DOMAIN,
            )


class Cs11ExpiredOperationLifecycleTests(
    unittest.IsolatedAsyncioTestCase
):
    def context(self, interaction="turn-2"):
        return ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref=interaction,
            interaction_source="request_header",
        )

    async def test_expired_operation_blocks_before_backend_calls(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "e" * 20

        registry.record(
            operation_id=op,
            operation_type=OPERATION_TYPE,
            domain=DOMAIN,
            context=self.context("turn-1"),
            expires_at="2000-01-01T00:00:00+00:00",
        )

        fake_client = AsyncMock()

        result = await confirm_then_execute(
            client=fake_client,
            registry=registry,
            destructive_execution_enabled=True,
            operation_id=op,
            context=self.context("turn-2"),
            expected_operation_type=OPERATION_TYPE,
            expected_domain=DOMAIN,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["code"],
            "prepared_operation_expired",
        )

        fake_client.confirm_operation.assert_not_awaited()
        fake_client.execute_operation.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
