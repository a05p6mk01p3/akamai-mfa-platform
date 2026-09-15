import unittest
from types import SimpleNamespace

from app.clients.eaa import EaaClient


class EaaResetContractTests(unittest.TestCase):
    def test_reset_contract_path_query_and_body(self):
        client = object.__new__(EaaClient)
        client.settings = SimpleNamespace(contract_id="contract-internal")
        captured = {}

        def fake_request(method, path, **kwargs):
            captured.update(method=method, path=path, kwargs=kwargs)
            return SimpleNamespace(status_code=200)

        client.request = fake_request

        status = client.reset_login_mfa("internal-reset-id")

        self.assertEqual(status, 200)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/crux/v1/mgmt-pop/tenant/mfa/reset")
        self.assertEqual(
            captured["kwargs"]["params"],
            {"contractId": "contract-internal"},
        )
        self.assertEqual(
            captured["kwargs"]["json"],
            {
                "otp_type": "login_mfa",
                "user_id": "internal-reset-id",
            },
        )


if __name__ == "__main__":
    unittest.main()
