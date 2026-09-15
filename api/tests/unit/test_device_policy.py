import unittest

from app.domain.akamai_mfa import AkamaiMfaFactorRecord
from app.domain.device_policy import DeviceClassification, classify_device


def factor(**kwargs):
    return AkamaiMfaFactorRecord(
        device_type=kwargs.get("device_type"),
        created_by=kwargs.get("created_by"),
        external_tag=kwargs.get("external_tag"),
        platform=kwargs.get("platform"),
        internal_device_id=kwargs.get("internal_device_id"),
        raw={},
    )


class DevicePolicyTests(unittest.TestCase):
    def test_user_authenticator_is_only_initially_eligible_class(self):
        decision = classify_device(factor(device_type="AKAMAI_AUTHENTICATOR", created_by="USER"))
        self.assertEqual(decision.classification, DeviceClassification.USER_AUTHENTICATOR)
        self.assertTrue(decision.reset_eligible)

    def test_external_eaa_is_protected_even_when_type_is_email(self):
        decision = classify_device(factor(device_type="EMAIL_ADDRESS", created_by="EXTERNAL", external_tag="eaa"))
        self.assertEqual(decision.classification, DeviceClassification.EXTERNAL_EAA)
        self.assertFalse(decision.reset_eligible)

    def test_other_external_is_protected(self):
        decision = classify_device(factor(device_type="EMAIL_ADDRESS", created_by="EXTERNAL", external_tag="other"))
        self.assertEqual(decision.classification, DeviceClassification.OTHER_EXTERNAL)
        self.assertFalse(decision.reset_eligible)

    def test_known_non_user_creator_is_admin_system(self):
        decision = classify_device(factor(device_type="AKAMAI_AUTHENTICATOR", created_by="ADMIN"))
        self.assertEqual(decision.classification, DeviceClassification.ADMIN_SYSTEM)
        self.assertFalse(decision.reset_eligible)

    def test_unknown_missing_fields_fail_closed(self):
        decision = classify_device(factor())
        self.assertEqual(decision.classification, DeviceClassification.UNKNOWN_PROTECTED)
        self.assertFalse(decision.reset_eligible)

    def test_user_unknown_type_fails_closed(self):
        decision = classify_device(factor(device_type="FUTURE_DEVICE", created_by="USER"))
        self.assertEqual(decision.classification, DeviceClassification.UNKNOWN_PROTECTED)
        self.assertFalse(decision.reset_eligible)


if __name__ == "__main__":
    unittest.main()
