import unittest

from app.tools import map_akamai_status, map_search_result


class MappingTests(unittest.TestCase):
    def test_search_preserves_ambiguous_and_whitelists_fields(self):
        body = {
            "status": "ambiguous",
            "query": "Example",
            "count": 2,
            "candidates": [
                {
                    "user_ref": "usr_safe",
                    "username": "u1",
                    "display_name": "Example One",
                    "internal_id": "must-not-leak",
                },
                {
                    "user_ref": "usr_safe2",
                    "username": "u2",
                    "display_name": "Example Two",
                },
            ],
        }
        result = map_search_result(body)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["count"], 2)
        self.assertNotIn("internal_id", result["candidates"][0])

    def test_status_preserves_backend_eligibility_without_recomputing(self):
        body = {
            "user_ref": "usr_safe",
            "account_present": True,
            "account_status": "ACTIVE",
            "business_state": None,
            "eligible_factor_count": 1,
            "selection_required": False,
            "factors": [
                {
                    "type": "AKAMAI_AUTHENTICATOR",
                    "created_by": "USER",
                    "classification": "USER_AUTHENTICATOR",
                    "reset_eligible": True,
                    "platform": "android",
                    "device_ref": "dev_safe",
                },
                {
                    "type": "EMAIL_ADDRESS",
                    "created_by": "EXTERNAL",
                    "external_source": "eaa",
                    "classification": "EXTERNAL_EAA",
                    "reset_eligible": False,
                    "device_ref": None,
                    "internal_device_id": "must-not-leak",
                },
            ],
        }
        result = map_akamai_status(body)
        self.assertEqual(result["eligible_factor_count"], 1)
        self.assertFalse(result["selection_required"])
        self.assertEqual(result["factors"][0]["device_ref"], "dev_safe")
        self.assertIsNone(result["factors"][1]["device_ref"])
        self.assertNotIn("internal_device_id", result["factors"][1])

    def test_protected_factor_device_ref_is_cleared_fail_closed(self):
        body = {
            "user_ref": "usr_safe",
            "account_present": True,
            "account_status": "PROVISIONED",
            "business_state": "already_awaiting_enrollment",
            "eligible_factor_count": 0,
            "selection_required": False,
            "factors": [
                {
                    "type": "EMAIL_ADDRESS",
                    "created_by": "EXTERNAL",
                    "external_source": "eaa",
                    "classification": "EXTERNAL_EAA",
                    "reset_eligible": False,
                    "device_ref": "dev_backend_bug",
                }
            ],
        }
        result = map_akamai_status(body)
        self.assertIsNone(result["factors"][0]["device_ref"])
        self.assertEqual(result["business_state"], "already_awaiting_enrollment")


if __name__ == "__main__":
    unittest.main()



class PrepareMappingTests(unittest.TestCase):
    def test_prepared_response_is_whitelisted(self):
        from app.tools import map_prepare_result

        result = map_prepare_result(
            {
                "status": "prepared",
                "confirmation_required": True,
                "operation_id": "op_" + "a" * 20,
                "operation_type": "AKAMAI_MFA_DEVICE_RESET",
                "domain": "akamai_mfa",
                "target": {
                    "user_ref": "usr_" + "b" * 20,
                    "username": "u1",
                    "device_id": "SECRET",
                    "eaa_reset_id": "SECRET2",
                },
                "expires_at": "2026-09-14T15:00:00+00:00",
                "request_id": "req-1",
                "internal": "do-not-pass",
            }
        )
        self.assertEqual(result["status"], "prepared")
        self.assertNotIn("device_id", result["target"])
        self.assertNotIn("eaa_reset_id", result["target"])
        self.assertNotIn("internal", result)
        self.assertTrue(result["confirmation_required"])

    def test_unknown_prepare_status_fails_closed(self):
        from app.tools import map_prepare_result

        result = map_prepare_result({"status": "mystery"})
        self.assertEqual(result["code"], "unexpected_api_contract")

    def test_retry_already_completed_requires_no_confirmation(self):
        from app.tools import map_prepare_result

        result = map_prepare_result(
            {
                "status": "already_completed",
                "confirmation_required": False,
                "operation_id": "op_" + "a" * 20,
                "operation_type": "AKAMAI_MFA_DEVICE_RESET",
                "domain": "akamai_mfa",
                "target": {
                    "user_ref": "usr_" + "b" * 20,
                    "username": "u1",
                },
                "outcome_code": "AKAMAI_MFA_POSTCHECK_TARGET_ABSENT",
            }
        )
        self.assertEqual(result["status"], "already_completed")
        self.assertFalse(result["confirmation_required"])



class LifecycleMappingTests(unittest.TestCase):
    def test_confirmation_contract_is_strict(self):
        from app.tools import map_confirmation_result
        op = "op_" + "a" * 20
        result = map_confirmation_result(
            {
                "operation_id": op,
                "operation_type": "EAA_NATIVE_MFA_OTP_RESET",
                "domain": "eaa_native_mfa",
                "status": "CONFIRMED",
                "confirmation_accepted": True,
                "confirmed_at": "2026-09-14T15:00:00+00:00",
                "expires_at": "2026-09-14T15:05:00+00:00",
            },
            operation_id=op,
            expected_operation_type="EAA_NATIVE_MFA_OTP_RESET",
            expected_domain="eaa_native_mfa",
        )
        self.assertEqual(result["status"], "CONFIRMED")

    def test_execution_output_does_not_pass_postcheck_details(self):
        from app.tools import map_execution_result
        op = "op_" + "a" * 20
        result = map_execution_result(
            {
                "operation_id": op,
                "operation_type": "AKAMAI_MFA_DEVICE_RESET",
                "domain": "akamai_mfa",
                "status": "SUCCEEDED",
                "outcome_code": "AKAMAI_MFA_POSTCHECK_TARGET_ABSENT",
                "post_check_result": {"internal_device_id": "SECRET"},
                "simulation": False,
            },
            operation_id=op,
            expected_operation_type="AKAMAI_MFA_DEVICE_RESET",
            expected_domain="akamai_mfa",
        )
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertNotIn("post_check_result", result)
        self.assertNotIn("SECRET", repr(result))
        self.assertFalse(result["automatic_destructive_retry_performed"])

    def test_reconfirmation_state_requires_new_prepare(self):
        from app.tools import map_execution_result
        op = "op_" + "a" * 20
        result = map_execution_result(
            {
                "operation_id": op,
                "operation_type": "AKAMAI_MFA_DEVICE_RESET",
                "domain": "akamai_mfa",
                "status": "REQUIRES_RECONFIRMATION",
                "outcome_code": "TARGET_REMAINS",
                "simulation": False,
            },
            operation_id=op,
            expected_operation_type="AKAMAI_MFA_DEVICE_RESET",
            expected_domain="akamai_mfa",
        )
        self.assertIn("child prepare", result["message"])
