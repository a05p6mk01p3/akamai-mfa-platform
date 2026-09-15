import ast
from pathlib import Path
import unittest


SERVER = Path(__file__).parents[1] / "app" / "server.py"


class ServerContractStaticTests(unittest.TestCase):
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

    def public_args(self, name):
        return [
            arg.arg
            for arg in self.functions[name].args.args
            if arg.arg != "ctx"
        ]

    def test_exact_six_frozen_public_tool_names(self):
        self.assertEqual(
            set(self.functions),
            {
                "search_eaa_user",
                "prepare_eaa_otp_reset",
                "reset_eaa_otp",
                "get_akamai_mfa_status",
                "prepare_akamai_mfa_device_reset",
                "reset_akamai_mfa_device",
            },
        )

    def test_destructive_tools_have_no_confirmed_argument(self):
        for name in ("reset_eaa_otp", "reset_akamai_mfa_device"):
            args = self.public_args(name)
            self.assertEqual(args, ["operation_id"])
            self.assertNotIn("confirmed", args)

    def test_context_is_injected_not_public_interaction_argument(self):
        for name, node in self.functions.items():
            all_args = [arg.arg for arg in node.args.args]
            self.assertIn("ctx", all_args, name)
            public = self.public_args(name)
            self.assertNotIn("ctx", public)
            self.assertNotIn("interaction_ref", public)
            self.assertNotIn("interaction_id", public)

    def test_no_tool_accepts_raw_internal_identifier_names(self):
        forbidden = {
            "device_id",
            "deviceId",
            "contract_id",
            "contractId",
            "directory_id",
            "directoryId",
            "user_id",
            "userId",
        }
        for name in self.functions:
            names = set(self.public_args(name))
            self.assertFalse(
                names & forbidden,
                (name, names & forbidden),
            )

    def test_transport_baseline_is_stateless_streamable_http_json(self):
        compact = self.source.replace(" ", "")
        self.assertIn('transport="streamable-http"', compact)
        self.assertIn("json_response=True", compact)
        self.assertIn("stateless_http=True", compact)
        self.assertNotIn("stateless_http=False", compact)

    def test_attestation_probe_logs_fingerprint_not_raw_value(self):
        self.assertIn("fingerprint=%s", self.source)
        self.assertIn(
            "interaction_fingerprint(context.interaction_ref)",
            self.source,
        )
        self.assertNotIn(
            '"interaction_attestation raw=%s"',
            self.source,
        )

    def test_cs04_prepare_tools_still_do_not_confirm_or_execute(self):
        for name in (
            "prepare_eaa_otp_reset",
            "prepare_akamai_mfa_device_reset",
        ):
            segment = ast.get_source_segment(
                self.source,
                self.functions[name],
            ) or ""
            self.assertIn("require_interaction=True", segment)
            self.assertIn("await client.prepare_", segment)
            self.assertNotIn("client.confirm", segment)
            self.assertNotIn("client.execute", segment)

    def test_cs04_reset_tools_map_only_to_internal_confirm_execute_helper(self):
        for name in (
            "reset_eaa_otp",
            "reset_akamai_mfa_device",
        ):
            segment = ast.get_source_segment(
                self.source,
                self.functions[name],
            ) or ""
            self.assertIn("require_interaction=True", segment)
            self.assertIn("confirm_then_execute", segment)
            self.assertNotIn("device_ref", self.public_args(name))
            self.assertEqual(self.public_args(name), ["operation_id"])

    def test_cs04_server_delegates_lifecycle_to_internal_helper(self):
        self.assertIn("from .lifecycle import confirm_then_execute", self.source)
        self.assertIn("destructive_execution_enabled=", self.source)

    def test_destructive_execution_is_explicitly_config_gated(self):
        self.assertIn('settings.destructive_execution_mode == "enabled"', self.source)


if __name__ == "__main__":
    unittest.main()
