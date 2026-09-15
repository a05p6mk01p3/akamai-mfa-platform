import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.context import RequestBoundContextProvider, TrustedContextUnavailable


class Cs05TrustedContextTests(unittest.TestCase):
    def request_settings(self):
        return Settings(
            api_url="http://api:8000",
            api_timeout=20,
            mcp_host="0.0.0.0",
            mcp_port=9000,
            log_level="INFO",
            api_actor="static-actor-must-be-ignored",
            api_session="static-session-must-be-ignored",
            interaction_attestation_mode="request_header",
            interaction_header_name="X-MFA-Interaction",
            log_attestation_probe=False,
            destructive_execution_mode="disabled",
            trusted_context_mode="request_headers",
            actor_header_name="X-MFA-Actor",
            session_header_name="X-MFA-Session",
        )

    def test_request_headers_override_and_ignore_static_context(self):
        provider = RequestBoundContextProvider(self.request_settings())
        context = provider.current(SimpleNamespace(headers={
            "X-MFA-Actor": "librechat-user-123",
            "X-MFA-Session": "conversation-456",
            "X-MFA-Interaction": "message-789",
        }), require_interaction=True)
        self.assertEqual(context.actor, "librechat-user-123")
        self.assertEqual(context.session, "conversation-456")
        self.assertEqual(context.interaction_ref, "message-789")
        self.assertEqual(context.actor_source, "request_header")
        self.assertEqual(context.session_source, "request_header")

    def test_missing_actor_or_session_fails_closed(self):
        provider = RequestBoundContextProvider(self.request_settings())
        for headers in ({}, {"X-MFA-Actor": "u"}, {"X-MFA-Session": "c"}):
            with self.subTest(headers=headers):
                with self.assertRaises(TrustedContextUnavailable):
                    provider.current(SimpleNamespace(headers=headers))

    def test_unresolved_librechat_placeholder_fails_closed(self):
        provider = RequestBoundContextProvider(self.request_settings())
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(SimpleNamespace(headers={
                "X-MFA-Actor": "{{LIBRECHAT_USER_ID}}",
                "X-MFA-Session": "conversation-456",
            }))
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(SimpleNamespace(headers={
                "X-MFA-Actor": "user-123",
                "X-MFA-Session": "{{LIBRECHAT_BODY_CONVERSATIONID}}",
            }))

    def test_actor_session_control_characters_fail_closed(self):
        provider = RequestBoundContextProvider(self.request_settings())
        with self.assertRaises(TrustedContextUnavailable):
            provider.current(SimpleNamespace(headers={
                "X-MFA-Actor": "user\nforged",
                "X-MFA-Session": "conversation-456",
            }))

    def test_static_mode_remains_explicit_compatibility_path(self):
        settings = self.request_settings()
        settings = Settings(**{**settings.__dict__, "trusted_context_mode": "static"})
        context = RequestBoundContextProvider(settings).current(SimpleNamespace(headers={
            "X-MFA-Actor": "request-user",
            "X-MFA-Session": "request-session",
        }))
        self.assertEqual(context.actor, "static-actor-must-be-ignored")
        self.assertEqual(context.actor_source, "deployment_static")

    def test_from_env_accepts_request_header_context_mode(self):
        with patch.dict(os.environ, {
            "MCP_TRUSTED_CONTEXT_MODE": "request_headers",
            "MCP_ACTOR_HEADER_NAME": "X-Test-Actor",
            "MCP_SESSION_HEADER_NAME": "X-Test-Session",
            "MCP_TRUSTED_INGRESS_MODE": "shared_secret",
            "MCP_TRUSTED_INGRESS_SECRET": "a" * 32,
        }, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.trusted_context_mode, "request_headers")
        self.assertEqual(settings.actor_header_name, "X-Test-Actor")
        self.assertEqual(settings.session_header_name, "X-Test-Session")

    def test_invalid_trusted_context_mode_rejected(self):
        with patch.dict(os.environ, {"MCP_TRUSTED_CONTEXT_MODE": "magic"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
