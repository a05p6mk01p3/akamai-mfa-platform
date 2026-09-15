import unittest
from types import SimpleNamespace

from app.domain.akamai_mfa import AkamaiMfaFactorRecord
from app.domain.device_policy import classify_device
from app.services.akamai_mfa import ObservedFactor
from app.references.service import SafeReferenceService, UnsafeReferenceRequest


class _Repo:
    def issue(self, **kwargs):
        return kwargs


class SafeReferencePolicyTests(unittest.TestCase):
    def factor(self, created_by, device_type, external_tag=None, device_id="d1"):
        rec = AkamaiMfaFactorRecord(
            device_type=device_type,
            created_by=created_by,
            external_tag=external_tag,
            platform=None,
            internal_device_id=device_id,
            raw={},
        )
        decision = classify_device(rec)
        return ObservedFactor(
            type=rec.device_type,
            created_by=rec.created_by,
            external_source=rec.external_tag,
            platform=rec.platform,
            classification=decision.classification,
            reset_eligible=decision.reset_eligible,
            internal=rec,
        )

    def test_protected_external_factor_cannot_receive_device_ref(self):
        service = SafeReferenceService(_Repo())
        with self.assertRaises(UnsafeReferenceRequest):
            service.issue_device_ref(
                self.factor("EXTERNAL", "EMAIL_ADDRESS", "eaa"),
                actor_context={"actor": "x"},
                session_context={"session": "s"},
                target_identity={"username": "u"},
            )

    def test_eligible_authenticator_can_be_bound_to_internal_device(self):
        service = SafeReferenceService(_Repo())
        result = service.issue_device_ref(
            self.factor("USER", "AKAMAI_AUTHENTICATOR"),
            actor_context={"actor": "x"},
            session_context={"session": "s"},
            target_identity={"username": "u"},
        )
        self.assertEqual(result["reference_type"].value, "DEVICE")
        self.assertEqual(result["internal_target"]["device_id"], "d1")


if __name__ == "__main__":
    unittest.main()
