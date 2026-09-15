import unittest
from app.operations.models import OperationStatus


class OperationModelTests(unittest.TestCase):
    def test_frozen_states_are_represented(self):
        self.assertEqual(OperationStatus.PREPARED.value, "PREPARED")
        self.assertEqual(OperationStatus.CONFIRMED.value, "CONFIRMED")
        self.assertEqual(OperationStatus.EXECUTING.value, "EXECUTING")
        self.assertEqual(OperationStatus.REQUIRES_RECONFIRMATION.value, "REQUIRES_RECONFIRMATION")


if __name__ == "__main__":
    unittest.main()
