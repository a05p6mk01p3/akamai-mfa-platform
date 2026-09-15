import ast
from pathlib import Path
import unittest

LIFECYCLE = Path(__file__).parents[1] / "app" / "lifecycle.py"

class LifecycleStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LIFECYCLE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_confirm_precedes_execute(self):
        self.assertLess(self.source.index("client.confirm_operation"), self.source.index("client.execute_operation"))

    def test_no_verify_or_retry_prepare(self):
        self.assertNotIn("client.verify", self.source)
        self.assertNotIn("prepare_retry", self.source)

    def test_transport_uncertainty_observes_without_destructive_retry(self):
        self.assertIn("client.get_operation_status", self.source)
        self.assertEqual(self.source.count("client.execute_operation"), 1)
        self.assertEqual(self.source.count("client.confirm_operation"), 1)

if __name__ == "__main__":
    unittest.main()
