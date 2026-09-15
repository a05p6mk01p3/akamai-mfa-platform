import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.context import (
    RequestBoundContextProvider,
    TrustedIngressUnavailable,
)


SECRET = "0123456789abcdef0123456789abcdef"


class Cs06TrustedIngressTests(unittest.TestCase):
    def settings(self, *, mode="shared_secret", secret=SECRET):
        return Settings(
            api_url="http://api:8000",
            api_timeout=20,
            mcp_host="0.0.0.0",
            mcp_port=9000,
            log_level="INFO",
            api_actor=None,
            api_session=None,
            interaction_attestation_mode="request_header",
            interaction_header_name="X-MFA-Interaction",
            log_attestation_probe=False,
            destructive_execution_mode="disabled",
            trusted_context_mode="request_headers",
            actor_header_name="X-MFA-Actor",
            session_header_name="X-MFA-Session",
            trusted_ingress_mode=mode,
            trusted_ingress_header_name="X-MFA-Ingress-Token",
            trusted_ingress_secret=secret,
        )

    def headers(self, token=SECRET):
        return {
            "X-MFA-Ingress-Token": token,
            "X-MFA-Actor": "user-123",
            "X-MFA-Session": "conversation-456",
            "X-MFA-Interaction": "message-789",
        }

    def test_valid_shared_secret_allows_context(self):
        provider = RequestBoundContextProvider(self.settings())
        ctx = provider.current(
            SimpleNamespace(headers=self.headers()),
            require_interaction=True,
        )
        self.assertEqual(ctx.actor, "user-123")
        self.assertEqual(ctx.session, "conversation-456")
        self.assertEqual(ctx.interaction_ref, "message-789")

    def test_missing_ingress_secret_header_fails_before_actor_session(self):
        provider = RequestBoundContextProvider(self.settings())
        headers = self.headers()
        headers.pop("X-MFA-Ingress-Token")
        with self.assertRaises(TrustedIngressUnavailable):
            provider.current(SimpleNamespace(headers=headers))

    def test_wrong_ingress_secret_header_fails_closed(self):
        provider = RequestBoundContextProvider(self.settings())
        with self.assertRaises(TrustedIngressUnavailable):
            provider.current(
                SimpleNamespace(headers=self.headers("x" * 32))
            )

    def test_ingress_header_lookup_is_case_insensitive(self):
        provider = RequestBoundContextProvider(self.settings())
        headers = self.headers()
        token = headers.pop("X-MFA-Ingress-Token")
        headers["x-mfa-ingress-token"] = token
        ctx = provider.current(SimpleNamespace(headers=headers))
        self.assertEqual(ctx.actor, "user-123")

    def test_request_headers_mode_requires_shared_secret_at_startup(self):
        with patch.dict(
            os.environ,
            {"MCP_TRUSTED_CONTEXT_MODE": "request_headers"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_shared_secret_requires_minimum_length(self):
        with patch.dict(
            os.environ,
            {
                "MCP_TRUSTED_CONTEXT_MODE": "request_headers",
                "MCP_TRUSTED_INGRESS_MODE": "shared_secret",
                "MCP_TRUSTED_INGRESS_SECRET": "short",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_shared_secret_can_be_loaded_from_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(SECRET + "\n")
            path = f.name
        try:
            with patch.dict(
                os.environ,
                {
                    "MCP_TRUSTED_CONTEXT_MODE": "request_headers",
                    "MCP_TRUSTED_INGRESS_MODE": "shared_secret",
                    "MCP_TRUSTED_INGRESS_SECRET_FILE": path,
                },
                clear=True,
            ):
                settings = Settings.from_env()
            self.assertEqual(settings.trusted_ingress_secret, SECRET)
        finally:
            os.unlink(path)

    def test_secret_env_and_file_are_mutually_exclusive(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(SECRET)
            path = f.name
        try:
            with patch.dict(
                os.environ,
                {
                    "MCP_TRUSTED_CONTEXT_MODE": "request_headers",
                    "MCP_TRUSTED_INGRESS_MODE": "shared_secret",
                    "MCP_TRUSTED_INGRESS_SECRET": SECRET,
                    "MCP_TRUSTED_INGRESS_SECRET_FILE": path,
                },
                clear=True,
            ):
                with self.assertRaises(ValueError):
                    Settings.from_env()
        finally:
            os.unlink(path)

    def test_static_context_can_keep_ingress_disabled_for_dev_compatibility(self):
        with patch.dict(
            os.environ,
            {
                "MCP_TRUSTED_CONTEXT_MODE": "static",
                "MCP_API_ACTOR": "dev-actor",
                "MCP_API_SESSION": "dev-session",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.trusted_ingress_mode, "disabled")


if __name__ == "__main__":
    unittest.main()
