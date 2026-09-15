import inspect
import unittest

import app.api.v2.operations as operation_routes
from app.clients.akamai_mfa import AkamaiMfaClient
from app.clients.eaa import EaaClient


class ConfirmContractRegressionTests(unittest.TestCase):
    def test_confirm_route_still_exists_after_execute_is_added(self):
        source = inspect.getsource(operation_routes).lower()
        self.assertIn("/{operation_id}/confirm", source)
        self.assertIn("/{operation_id}/execute", source)

    def test_no_public_confirmed_true_body_contract(self):
        source = inspect.getsource(operation_routes).lower()
        self.assertNotIn("confirmed=true", source)
        self.assertNotIn("confirmed: bool", source)

    def test_akamai_client_has_only_domain_specific_delete_primitive(self):
        methods = {
            name.lower()
            for name, _ in inspect.getmembers(AkamaiMfaClient, inspect.isfunction)
        }
        self.assertIn("delete_device", methods)
        self.assertFalse(any("delete_user" in name for name in methods))

    def test_eaa_client_has_only_domain_specific_reset_primitive(self):
        methods = {
            name.lower()
            for name, _ in inspect.getmembers(EaaClient, inspect.isfunction)
        }
        self.assertIn("reset_login_mfa", methods)
        self.assertNotIn("delete", " ".join(methods))


if __name__ == "__main__":
    unittest.main()
