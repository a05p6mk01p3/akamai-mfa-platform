import unittest

from app.context import interaction_fingerprint


class InteractionFingerprintTests(unittest.TestCase):
    def test_same_reference_same_fingerprint_with_same_key(self):
        key = b"k" * 32
        a = interaction_fingerprint("interaction-a", key=key)
        b = interaction_fingerprint("interaction-a", key=key)
        self.assertEqual(a, b)

    def test_different_references_different_fingerprints(self):
        key = b"k" * 32
        a = interaction_fingerprint("interaction-a", key=key)
        b = interaction_fingerprint("interaction-b", key=key)
        self.assertNotEqual(a, b)

    def test_default_fingerprint_is_short_hex_and_not_raw(self):
        raw = "very-sensitive-interaction-reference"
        fp = interaction_fingerprint(raw)
        self.assertRegex(fp, r"^[0-9a-f]{12}$")
        self.assertNotIn(raw, fp)

    def test_invalid_length_rejected(self):
        with self.assertRaises(ValueError):
            interaction_fingerprint(
                "interaction-a",
                key=b"k" * 32,
                length=4,
            )


if __name__ == "__main__":
    unittest.main()
