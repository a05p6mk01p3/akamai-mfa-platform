import inspect
import unittest

import app.api.v2.schemas as schemas
import app.api.v2.operations as operations


class InternalPostcheckBaselineTests(unittest.TestCase):
    def test_public_operation_schema_has_no_destructive_target(self):
        fields = schemas.OperationStatusResponse.model_fields
        self.assertNotIn("destructive_target", fields)
        self.assertNotIn("postcheck_factor_baseline", fields)

    def test_operation_route_never_serializes_destructive_target(self):
        source = inspect.getsource(operations)
        self.assertNotIn("destructive_target=", source)
        self.assertNotIn("postcheck_factor_baseline", source)


if __name__ == "__main__":
    unittest.main()
