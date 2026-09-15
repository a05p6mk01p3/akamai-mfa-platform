import unittest
from types import SimpleNamespace

from app.config import Settings
from app.context import RequestBoundContextProvider, TrustedContextUnavailable


class ContextTests(unittest.TestCase):
    def settings(
        self,
        actor=None,
        session=None,
        *,
        mode="disabled",
        header="X-MFA-Interaction",
    ):
        return Settings(
            api_url="http://api:8000",
            api_timeout=20,
            mcp_host="0.0.0.0",
            mcp_port=9000,
            log_level="INFO",
            api_actor=actor,
            api_session=session,
            interaction_attestation_mode=mode,
            interaction_header_name=header,
            log_attestation_probe=False,
            destructive_execution_mode="disabled",
        )

    def test_missing_actor_session_fails_closed(self):
        provider = RequestBoundContextProvider(self.settings())
        with self.assertRaises(TrustedContextUnavailable):
            provider.current()

    def test_readonly_context_generates_only_actor_session_headers(self):
        provider = RequestBoundContextProvider(
            self.settings("actor", "session")
        )
        context = provider.current()
        self.assertEqual(
            context.headers(),
            {
                "X-MFA-Actor": "actor",
                "X-MFA-Session": "session",
            },
        )
        self.assertIsNone(context.interaction_ref)

    def test_request_header_attestation_is_request_bound(self):
        provider = RequestBoundContextProvider(
            self.settings(
                "actor",
                "session",
                mode="request_header",
            )
        )
        ctx = SimpleNamespace(
            headers={"x-mfa-interaction": "interaction-123"},
            session_id=None,
        )
        context = provider.current(
            ctx,
            require_interaction=True,
        )
        self.assertEqual(context.interaction_ref, "interaction-123")
        self.assertEqual(
            context.interaction_source,
            "request_header",
        )

    def test_interaction_is_not_forwarded_by_readonly_headers(self):
        provider = RequestBoundContextProvider(
            self.settings(
                "actor",
                "session",
                mode="request_header",
            )
        )
        ctx = SimpleNamespace(
            headers={"X-MFA-Interaction": "interaction-123"},
        )
        context = provider.current(
            ctx,
            require_interaction=True,
        )
        self.assertNotIn("X-MFA-Interaction", context.headers())
        self.assertEqual(
            context.destructive_context_headers()["X-MFA-Interaction"],
            "interaction-123",
        )

    def test_required_interaction_fails_when_mode_disabled(self):
        provider = RequestBoundContextProvider(
            self.settings("actor", "session")
        )
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(
                SimpleNamespace(
                    headers={"X-MFA-Interaction": "forged"},
                ),
                require_interaction=True,
            )

    def test_required_interaction_fails_when_header_missing(self):
        provider = RequestBoundContextProvider(
            self.settings(
                "actor",
                "session",
                mode="request_header",
            )
        )
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(
                SimpleNamespace(headers={}),
                require_interaction=True,
            )

    def test_control_character_is_rejected(self):
        provider = RequestBoundContextProvider(
            self.settings(
                "actor",
                "session",
                mode="request_header",
            )
        )
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(
                SimpleNamespace(
                    headers={
                        "X-MFA-Interaction": "bad\ninteraction",
                    }
                ),
                require_interaction=True,
            )


if __name__ == "__main__":
    unittest.main()
