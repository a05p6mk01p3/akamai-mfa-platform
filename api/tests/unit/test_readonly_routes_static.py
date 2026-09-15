import inspect
import unittest

import app.api.v2.akamai_mfa as akamai_routes
import app.api.v2.eaa as eaa_routes
from app.clients.akamai_mfa import AkamaiMfaClient
from app.clients.eaa import EaaClient


class ReadOnlyRouteStaticTests(unittest.TestCase):
    def test_readonly_routes_never_call_eaa_reset(self):
        sources = inspect.getsource(akamai_routes) + inspect.getsource(eaa_routes)
        self.assertNotIn("reset_login_mfa", sources)

    def test_v2_route_modules_contain_no_delete_http_decorator(self):
        sources = inspect.getsource(akamai_routes) + inspect.getsource(eaa_routes)
        self.assertNotIn("@router.delete", sources.lower())


if __name__ == "__main__":
    unittest.main()
