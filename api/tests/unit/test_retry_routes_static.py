import inspect
import unittest

import app.api.v2.operations as routes


class RetryRouteStaticTests(unittest.TestCase):
    def test_retry_prepare_route_exists(self):
        source = inspect.getsource(routes)
        self.assertIn(
            '"/{parent_operation_id}/retry/prepare"',
            source,
        )

    def test_retry_prepare_requires_interaction_context(self):
        source = inspect.getsource(routes.prepare_retry_operation)
        self.assertIn("require_interaction_context", source)
        self.assertNotIn("device_ref", source)
        self.assertNotIn("device_id", source)
        self.assertNotIn("confirmed", source)
        self.assertNotIn("target_override", source)

    def test_retry_prepare_does_not_execute(self):
        source = inspect.getsource(routes.prepare_retry_operation)
        self.assertNotIn("execute_operation", source)
        self.assertNotIn(".execute", source)


if __name__ == "__main__":
    unittest.main()
