import ast
from pathlib import Path
import unittest

from app.validation import normalize_user_ref


PROBE = Path(__file__).parents[1] / "scripts" / "probe_interaction_header.py"


class ProbeInputTests(unittest.TestCase):
    def test_probe_uses_syntactically_valid_user_ref(self):
        tree = ast.parse(PROBE.read_text(encoding="utf-8"))
        value = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(
                    isinstance(target, ast.Name)
                    and target.id == "PROBE_USER_REF"
                    for target in node.targets
                ):
                    value = ast.literal_eval(node.value)
                    break

        self.assertIsInstance(value, str)
        self.assertEqual(normalize_user_ref(value), value)

    def test_probe_safe_ref_is_fictitious_and_not_environment_derived(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('PROBE_USER_REF = "usr_00000000000000000000"', source)
        self.assertNotIn('os.getenv("PROBE_USER_REF"', source)


if __name__ == "__main__":
    unittest.main()
