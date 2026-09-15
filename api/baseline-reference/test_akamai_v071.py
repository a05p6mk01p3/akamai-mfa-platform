import sys
import types
import unittest

# Stub mínimo para executar testes de parsing sem instalar edgegrid-python no host de build.
akamai_pkg = types.ModuleType("akamai")
edgegrid_mod = types.ModuleType("akamai.edgegrid")
class EdgeGridAuth:  # pragma: no cover - apenas stub de import
    def __init__(self, *args, **kwargs):
        pass
edgegrid_mod.EdgeGridAuth = EdgeGridAuth
akamai_pkg.edgegrid = edgegrid_mod
sys.modules.setdefault("akamai", akamai_pkg)
sys.modules.setdefault("akamai.edgegrid", edgegrid_mod)

from app.akamai import AkamaiEaaClient, AkamaiError


EAA_SAMPLE = {
    "meta": {"total_count": 1},
    "objects": [
        {
            "username": "a0000001",
            "samaccountname": "A0000001",
            "uuid_url": "m3RZGvrQSGilGPD_dRZ-XQ",
            "first_name": "Test",
            "last_name": "User",
            "mfa": {"admin_mfa": False, "login_mfa": True},
        }
    ],
}

AMFA_SAMPLE = {
    "users": [
        {
            "userId": "user_example",
            "username": "80000001",
            "devices": [],
            "deviceCount": 1,
            "userStatus": "ACTIVE",
        }
    ],
    "totalItems": 1,
    "totalPages": 1,
}

AMFA_SYNCED_SAMPLE = {
    "users": [
        {
            "userId": "user_synced_example",
            "username": "a0000001",
            "devices": [],
            "deviceCount": 2,
            "importSource": {"id": "eaa", "type": "EAA"},
        }
    ]
}


class AkamaiParserTests(unittest.TestCase):
    def test_tenant_envelope_and_uuid_url(self):
        objects = AkamaiEaaClient._objects(EAA_SAMPLE)
        self.assertEqual(len(objects), 1)
        match = AkamaiEaaClient._to_match(objects[0])
        self.assertEqual(match.username, "a0000001")
        self.assertEqual(match.reset_user_id, "m3RZGvrQSGilGPD_dRZ-XQ")
        self.assertEqual(match.display_name, "Test User")
        self.assertTrue(match.login_mfa)

    def test_exact_match_is_case_insensitive(self):
        match = AkamaiEaaClient._to_match(EAA_SAMPLE["objects"][0])
        selected = AkamaiEaaClient.select_exact_user("A0000001", [match])
        self.assertEqual(selected.uuid_url, "m3RZGvrQSGilGPD_dRZ-XQ")

    def test_partial_match_is_rejected(self):
        match = AkamaiEaaClient._to_match(EAA_SAMPLE["objects"][0])
        with self.assertRaises(AkamaiError) as ctx:
            AkamaiEaaClient.select_exact_user("A000", [match])
        self.assertEqual(ctx.exception.status_code, 409)

    def test_missing_eaa_user_is_404(self):
        with self.assertRaises(AkamaiError) as ctx:
            AkamaiEaaClient.select_exact_user("A0000001", [])
        self.assertEqual(ctx.exception.status_code, 404)

    def test_amfa_device_count_is_used_even_when_devices_list_is_empty(self):
        items = AkamaiEaaClient._objects(AMFA_SAMPLE)
        match = AkamaiEaaClient._to_amfa_match(items[0])
        self.assertEqual(match.username, "80000001")
        self.assertEqual(match.user_id, "user_example")
        self.assertEqual(match.device_count, 1)

    def test_amfa_import_source_and_count(self):
        match = AkamaiEaaClient._to_amfa_match(AMFA_SYNCED_SAMPLE["users"][0])
        self.assertEqual(match.import_source_type, "EAA")
        self.assertEqual(match.device_count, 2)

    def test_amfa_exact_match_case_insensitive(self):
        match = AkamaiEaaClient._to_amfa_match(AMFA_SYNCED_SAMPLE["users"][0])
        selected = AkamaiEaaClient.select_exact_amfa_user("A0000001", [match])
        self.assertIsNotNone(selected)
        self.assertEqual(selected.user_id, "user_synced_example")

    def test_amfa_absence_is_not_error(self):
        selected = AkamaiEaaClient.select_exact_amfa_user("80000001", [])
        self.assertIsNone(selected)

    def test_amfa_missing_device_count_fails_closed(self):
        match = AkamaiEaaClient._to_amfa_match({"userId": "user_x", "username": "u1", "devices": []})
        with self.assertRaises(AkamaiError) as ctx:
            AkamaiEaaClient.select_exact_amfa_user("u1", [match])
        self.assertEqual(ctx.exception.status_code, 502)

    def test_amfa_ambiguous_match_is_rejected(self):
        a = AkamaiEaaClient._to_amfa_match({"userId": "u1", "username": "same", "deviceCount": 1})
        b = AkamaiEaaClient._to_amfa_match({"userId": "u2", "username": "same", "deviceCount": 1})
        with self.assertRaises(AkamaiError) as ctx:
            AkamaiEaaClient.select_exact_amfa_user("same", [a, b])
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()

class _FakeResponse:
    status_code = 200
    def json(self):
        return {"result": {"id": "user_example"}}
    @property
    def text(self):
        return ''


def test_delete_response_extracts_result_id(monkeypatch):
    client = object.__new__(AkamaiEaaClient)
    client.settings = types.SimpleNamespace(contract_id="W-TEST")
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: _FakeResponse())
    result = client.delete_amfa_user("user_example")
    assert result.status_code == 200
    assert result.result_id == "user_example"
