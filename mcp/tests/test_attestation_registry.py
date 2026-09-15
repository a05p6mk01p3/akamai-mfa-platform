import unittest

from app.attestation import (
    PreparedInteractionAlreadyClaimed,
    PreparedInteractionContextMismatch,
    PreparedInteractionLaterRequired,
    PreparedInteractionRegistry,
    PreparedInteractionTypeMismatch,
    PreparedInteractionUnknown,
)
from app.context import ApiRequestContext


class PreparedInteractionRegistryTests(unittest.TestCase):
    def context(self, actor="actor", session="session", interaction="turn-1"):
        return ApiRequestContext(
            actor=actor,
            session=session,
            interaction_ref=interaction,
            interaction_source="request_header",
        )

    def record(self, registry, op="op_" + "a" * 20, interaction="turn-1"):
        return registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context(interaction=interaction),
            expires_at="2099-01-01T00:00:00+00:00",
        )

    def test_same_interaction_is_blocked(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        self.record(registry, op)
        with self.assertRaises(PreparedInteractionLaterRequired):
            registry.claim_for_reset(
                operation_id=op,
                context=self.context(interaction="turn-1"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )

    def test_later_interaction_claims_once(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        self.record(registry, op)
        record = registry.claim_for_reset(
            operation_id=op,
            context=self.context(interaction="turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
            expected_domain="eaa_native_mfa",
        )
        self.assertEqual(record.local_state, "CLAIMED")
        with self.assertRaises(PreparedInteractionAlreadyClaimed):
            registry.claim_for_reset(
                operation_id=op,
                context=self.context(interaction="turn-3"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )

    def test_release_claim_allows_future_human_retry(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        self.record(registry, op)
        registry.claim_for_reset(
            operation_id=op,
            context=self.context(interaction="turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
            expected_domain="eaa_native_mfa",
        )
        registry.release_claim(op)
        registry.claim_for_reset(
            operation_id=op,
            context=self.context(interaction="turn-3"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
            expected_domain="eaa_native_mfa",
        )

    def test_terminal_never_replays(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        self.record(registry, op)
        registry.claim_for_reset(
            operation_id=op,
            context=self.context(interaction="turn-2"),
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
            expected_domain="eaa_native_mfa",
        )
        registry.mark_terminal(op)
        with self.assertRaises(PreparedInteractionAlreadyClaimed):
            registry.claim_for_reset(
                operation_id=op,
                context=self.context(interaction="turn-3"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )

    def test_unknown_context_and_domain_fail_closed(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        with self.assertRaises(PreparedInteractionUnknown):
            registry.require_later_interaction(
                operation_id=op,
                context=self.context(interaction="turn-2"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )
        self.record(registry, op)
        with self.assertRaises(PreparedInteractionContextMismatch):
            registry.require_later_interaction(
                operation_id=op,
                context=self.context(actor="other", interaction="turn-2"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )
        with self.assertRaises(PreparedInteractionTypeMismatch):
            registry.require_later_interaction(
                operation_id=op,
                context=self.context(interaction="turn-2"),
                expected_operation_type="AKAMAI_MFA_DEVICE_RESET",
                expected_domain="akamai_mfa",
            )

    def test_expired_record_is_unavailable(self):
        registry = PreparedInteractionRegistry()
        op = "op_" + "a" * 20
        registry.record(
            operation_id=op,
            operation_type="EAA_NATIVE_MFA_OTP_RESET",
            domain="eaa_native_mfa",
            context=self.context(),
            expires_at="2000-01-01T00:00:00+00:00",
        )
        with self.assertRaises(PreparedInteractionUnknown):
            registry.require_later_interaction(
                operation_id=op,
                context=self.context(interaction="turn-2"),
                expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
                expected_domain="eaa_native_mfa",
            )

    def test_registry_pressure_fails_closed(self):
        registry = PreparedInteractionRegistry(max_entries=1)
        self.record(registry, "op_" + "a" * 20)
        with self.assertRaises(RuntimeError):
            self.record(registry, "op_" + "b" * 20, interaction="turn-2")


if __name__ == "__main__":
    unittest.main()
