import ast
from pathlib import Path
import unittest

SERVER = Path(__file__).parents[1] / "app" / "server.py"
CONTEXT = Path(__file__).parents[1] / "app" / "context.py"
CONFIG = Path(__file__).parents[1] / "app" / "config.py"


class Cs06StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_source = SERVER.read_text(encoding="utf-8")
        cls.context_source = CONTEXT.read_text(encoding="utf-8")
        cls.config_source = CONFIG.read_text(encoding="utf-8")
        tree = ast.parse(cls.server_source)
        cls.tools = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "tool"
                for dec in node.decorator_list
            )
        }

    def test_public_tools_never_accept_ingress_credentials(self):
        for name, node in self.tools.items():
            args = [arg.arg for arg in node.args.args if arg.arg != "ctx"]
            for forbidden in ("ingress_token", "ingress_secret", "trusted_ingress"):
                self.assertNotIn(forbidden, args, name)

    def test_ingress_is_validated_before_actor_session(self):
        current_start = self.context_source.index("def current(")
        segment = self.context_source[current_start:current_start + 900]
        self.assertLess(
            segment.index("self._validate_trusted_ingress(request_context)"),
            segment.index("self._actor_session("),
        )

    def test_shared_secret_uses_constant_time_compare(self):
        self.assertIn("hmac.compare_digest(provided, expected)", self.context_source)

    def test_server_returns_specific_ingress_error(self):
        self.assertIn('"code": "trusted_ingress_unavailable"', self.server_source)

    def test_ingress_secret_is_never_logged_or_fingerprinted(self):
        self.assertNotIn("trusted_ingress_secret=%s", self.server_source)
        self.assertNotIn("ingress_secret=%s", self.server_source)
        self.assertNotIn("interaction_fingerprint(settings.trusted_ingress_secret)", self.server_source)

    def test_request_header_context_requires_ingress_authentication(self):
        self.assertIn(
            'trusted_context_mode == "request_headers"',
            self.config_source,
        )
        self.assertIn(
            'trusted_ingress_mode != "shared_secret"',
            self.config_source,
        )


if __name__ == "__main__":
    unittest.main()
