import inspect
import unittest

import app.api.v2.prepare as prepare_routes
from app.clients.akamai_mfa import AkamaiMfaClient
from app.clients.eaa import EaaClient


class PrepareOnlyStaticTests(unittest.TestCase):
    def test_prepare_routes_do_not_call_mutating_primitive(self):
        source = inspect.getsource(prepare_routes).lower()
        self.assertNotIn("reset_login_mfa", source)
        self.assertNotIn("@router.delete", source)

    def test_prepare_routes_do_not_expose_execute_or_confirm(self):
        source = inspect.getsource(prepare_routes).lower()
        self.assertNotIn("/execute", source)
        self.assertNotIn("/confirm", source)
        self.assertNotIn("@router.delete", source)


if __name__ == "__main__":
    unittest.main()
