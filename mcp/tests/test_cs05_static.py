import ast
from pathlib import Path
import unittest

SERVER = Path(__file__).parents[1] / "app" / "server.py"


class Cs05StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "tool"
                for dec in node.decorator_list
            )
        }

    def test_public_tools_do_not_accept_actor_or_session_arguments(self):
        for name, node in self.functions.items():
            public = [arg.arg for arg in node.args.args if arg.arg != "ctx"]
            self.assertNotIn("actor", public, name)
            self.assertNotIn("session", public, name)
            self.assertNotIn("interaction_ref", public, name)

    def test_server_logs_only_fingerprints_for_request_context(self):
        self.assertIn("actor_fingerprint=%s", self.source)
        self.assertIn("session_fingerprint=%s", self.source)
        self.assertNotIn("actor=%s", self.source)
        self.assertNotIn("session=%s", self.source)


if __name__ == "__main__":
    unittest.main()
