import inspect
import unittest

from app.clients.akamai_mfa import AkamaiMfaClient
from app.clients.eaa import EaaClient


class DestructivePrimitiveBoundaryTests(unittest.TestCase):
    def test_only_domain_specific_primitives_exist(self):
        eaa_methods = {
            name for name, _ in inspect.getmembers(EaaClient, inspect.isfunction)
        }
        amfa_methods = {
            name for name, _ in inspect.getmembers(AkamaiMfaClient, inspect.isfunction)
        }

        self.assertIn("reset_login_mfa", eaa_methods)
        self.assertIn("delete_device", amfa_methods)
        self.assertFalse(any("delete_user" in name.lower() for name in amfa_methods))
        self.assertFalse(any("reset_all" in name.lower() for name in amfa_methods))


if __name__ == "__main__":
    unittest.main()
