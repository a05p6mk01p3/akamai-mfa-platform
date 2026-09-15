import inspect
import unittest

import app.api.v2.operations as routes
from app.clients.akamai_mfa import AkamaiMfaClient
from app.clients.eaa import EaaClient


class ExecutionSurfaceStaticTests(unittest.TestCase):
    def test_execute_route_accepts_no_target_override_model(self):
        source = inspect.getsource(routes)
        execute = source[source.index("def execute_operation"):source.index("def verify_operation")]
        self.assertNotIn("device_ref", execute)
        self.assertNotIn("device_id", execute)
        self.assertNotIn("target_override", execute)
        self.assertNotIn("confirmed", execute)

    def test_verify_route_is_separate_from_execute(self):
        source = inspect.getsource(routes).lower()
        self.assertIn("/{operation_id}/execute", source)
        self.assertIn("/{operation_id}/verify", source)

    def test_akamai_client_has_device_delete_but_no_account_delete(self):
        methods = {
            name.lower()
            for name, _ in inspect.getmembers(AkamaiMfaClient, inspect.isfunction)
        }
        self.assertIn("delete_device", methods)
        self.assertFalse(any("delete_user" in name for name in methods))

    def test_eaa_reset_primitive_is_domain_specific(self):
        methods = {
            name.lower()
            for name, _ in inspect.getmembers(EaaClient, inspect.isfunction)
        }
        self.assertIn("reset_login_mfa", methods)


if __name__ == "__main__":
    unittest.main()
