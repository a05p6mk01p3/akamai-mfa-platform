import unittest
from types import SimpleNamespace

from app.domain.akamai_mfa import AkamaiMfaFactorRecord
from app.domain.device_policy import classify_device
from app.references.service import SafeReferenceService
from app.services.akamai_mfa import ObservedFactor, AkamaiMfaStatus


class _Reference:
    def __init__(self, reference_id):
        self.reference_id = reference_id


class _Repo:
    def __init__(self):
        self.calls = []
        self.n = 0

    def issue(self, **kwargs):
        self.calls.append(kwargs)
        self.n += 1
        return _Reference(f"dev_safe_{self.n}")


def observed(created_by, device_type, external_tag=None, device_id="internal-device"):
    record = AkamaiMfaFactorRecord(
        device_type=device_type,
        created_by=created_by,
        external_tag=external_tag,
        platform="test",
        internal_device_id=device_id,
        raw={},
    )
    decision = classify_device(record)
    return ObservedFactor(
        type=record.device_type,
        created_by=record.created_by,
        external_source=record.external_tag,
        platform=record.platform,
        classification=decision.classification,
        reset_eligible=decision.reset_eligible,
        internal=record,
    )


class ReadOnlyReferenceViewTests(unittest.TestCase):
    def test_only_eligible_factor_gets_device_ref(self):
        repo = _Repo()
        refs = SafeReferenceService(repo)
        eligible = observed("USER", "AKAMAI_AUTHENTICATOR", device_id="secret-1")
        protected = observed("EXTERNAL", "EMAIL_ADDRESS", "eaa", device_id="secret-2")
        status = AkamaiMfaStatus(
            account_present=True,
            account_status="ACTIVE",
            business_state=None,
            factors=(eligible, protected),
            internal_account=None,
        )

        output = refs.reference_status_factors(
            status,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            target_identity={"user_ref": "usr_safe"},
        )

        self.assertEqual(output[0].device_ref, "dev_safe_1")
        self.assertIsNone(output[1].device_ref)
        self.assertEqual(len(repo.calls), 1)
        self.assertEqual(repo.calls[0]["internal_target"]["device_id"], "secret-1")

    def test_protected_factor_never_creates_repository_entry(self):
        repo = _Repo()
        refs = SafeReferenceService(repo)
        protected = observed("EXTERNAL", "EMAIL_ADDRESS", "eaa")
        status = AkamaiMfaStatus(
            account_present=True,
            account_status="PROVISIONED",
            business_state="already_awaiting_enrollment",
            factors=(protected,),
            internal_account=None,
        )
        output = refs.reference_status_factors(
            status,
            actor_context={"actor": "a"},
            session_context={"session": "s"},
            target_identity={"user_ref": "usr_safe"},
        )
        self.assertIsNone(output[0].device_ref)
        self.assertEqual(repo.calls, [])


if __name__ == "__main__":
    unittest.main()
