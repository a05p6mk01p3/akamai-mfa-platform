import unittest
from types import SimpleNamespace

from app.clients.akamai_mfa import AkamaiMfaClient


class AkamaiMfaDeleteContractTests(unittest.TestCase):
    def test_delete_device_contract_path_query_and_no_body(self):
        client = object.__new__(AkamaiMfaClient)
        client.settings = SimpleNamespace(contract_id="contract-internal")
        captured = {}

        def fake_request(method, path, **kwargs):
            captured.update(method=method, path=path, kwargs=kwargs)
            return SimpleNamespace(status_code=204)

        client.request = fake_request

        status = client.delete_device("device/id with spaces")

        self.assertEqual(status, 204)
        self.assertEqual(captured["method"], "DELETE")
        self.assertEqual(
            captured["path"],
            "/amfa/v1/devices/device%2Fid%20with%20spaces",
        )
        self.assertEqual(
            captured["kwargs"]["params"],
            {"contractId": "contract-internal"},
        )
        self.assertNotIn("json", captured["kwargs"])


if __name__ == "__main__":
    unittest.main()
