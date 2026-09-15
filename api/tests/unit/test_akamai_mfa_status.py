import unittest

from app.clients.akamai_mfa import AkamaiMfaClient
from app.domain.device_policy import DeviceClassification
from app.services.akamai_mfa import AkamaiMfaService


class AkamaiMfaStatusTests(unittest.TestCase):
    def test_parse_and_classify_authenticator_plus_protected_eaa(self):
        account = AkamaiMfaClient.parse_account({
            "userId": "internal-user-id",
            "username": "user123",
            "userStatus": "ACTIVE",
            "devices": [
                {
                    "deviceId": "internal-device-id",
                    "deviceType": "AKAMAI_AUTHENTICATOR",
                    "createdBy": "USER",
                    "platform": "Android",
                },
                {
                    "deviceId": "internal-external-id",
                    "deviceType": "EMAIL_ADDRESS",
                    "createdBy": "EXTERNAL",
                    "externalTag": "eaa",
                },
            ],
        })
        status = AkamaiMfaService.inspect_account(account)
        self.assertTrue(status.account_present)
        self.assertEqual(status.account_status, "ACTIVE")
        self.assertEqual(len(status.factors), 2)
        self.assertEqual(status.factors[0].classification, DeviceClassification.USER_AUTHENTICATOR)
        self.assertTrue(status.factors[0].reset_eligible)
        self.assertEqual(status.factors[1].classification, DeviceClassification.EXTERNAL_EAA)
        self.assertFalse(status.factors[1].reset_eligible)

    def test_provisioned_only_external_eaa_is_already_awaiting_enrollment(self):
        account = AkamaiMfaClient.parse_account({
            "userId": "internal-user-id",
            "username": "user123",
            "userStatus": "PROVISIONED",
            "devices": [
                {
                    "deviceType": "EMAIL_ADDRESS",
                    "createdBy": "EXTERNAL",
                    "externalTag": "eaa",
                }
            ],
        })
        status = AkamaiMfaService.inspect_account(account)
        self.assertEqual(status.business_state, "already_awaiting_enrollment")

    def test_no_account_is_distinct_from_provisioned(self):
        status = AkamaiMfaService.inspect_account(None)
        self.assertFalse(status.account_present)
        self.assertIsNone(status.account_status)

    def test_internal_ids_stay_only_on_internal_models(self):
        account = AkamaiMfaClient.parse_account({
            "userId": "upstream-user-id",
            "username": "user123",
            "devices": [{"deviceId": "upstream-device-id", "deviceType": "AKAMAI_AUTHENTICATOR", "createdBy": "USER"}],
        })
        status = AkamaiMfaService.inspect_account(account)
        self.assertEqual(status.internal_account.internal_user_id, "upstream-user-id")
        self.assertEqual(status.factors[0].internal.internal_device_id, "upstream-device-id")


if __name__ == "__main__":
    unittest.main()
