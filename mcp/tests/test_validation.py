import unittest

from app.validation import (
    normalize_device_ref,
    normalize_operation_id,
    normalize_query,
    normalize_user_ref,
)


class ValidationTests(unittest.TestCase):
    def test_query_accepts_name_search_with_spaces(self):
        self.assertEqual(normalize_query("  Example User  "), "Example User")

    def test_query_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            normalize_query("user\nname")

    def test_user_ref_requires_usr_prefix(self):
        good = "usr_" + "A" * 24
        self.assertEqual(normalize_user_ref(good), good)
        with self.assertRaises(ValueError):
            normalize_user_ref("dev_" + "A" * 24)

    def test_device_ref_requires_dev_prefix(self):
        good = "dev_" + "B" * 24
        self.assertEqual(normalize_device_ref(good), good)

    def test_operation_id_validation(self):
        good = "op_" + "C" * 24
        self.assertEqual(normalize_operation_id(good), good)


if __name__ == "__main__":
    unittest.main()
