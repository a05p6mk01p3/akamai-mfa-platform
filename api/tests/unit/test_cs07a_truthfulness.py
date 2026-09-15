import inspect
import unittest

import app.api.v2.operations as operation_routes
from app.api.v2.schemas import OperationExecutionResponse


class Cs07aTruthfulnessTests(unittest.TestCase):
    def test_execution_response_simulation_is_boolean_not_literal_true(self):
        annotation = OperationExecutionResponse.model_fields["simulation"].annotation
        self.assertIs(annotation, bool)

    def test_routes_derive_simulation_from_execution_backend(self):
        source = inspect.getsource(operation_routes)
        self.assertIn(
            'simulation=(settings().execution_backend == "simulation")',
            source,
        )

    def test_execute_still_accepts_no_body_target_override(self):
        source = inspect.getsource(operation_routes)
        execute = source[source.index("def execute_operation"):source.index("def verify_operation")]
        self.assertNotIn("device_ref", execute)
        self.assertNotIn("device_id", execute)
        self.assertNotIn("target_override", execute)


if __name__ == "__main__":
    unittest.main()
