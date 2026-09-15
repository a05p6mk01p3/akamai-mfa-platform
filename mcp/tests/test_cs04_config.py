import os
import unittest
from unittest.mock import patch

from app.config import Settings


class Cs04ConfigTests(unittest.TestCase):
    def test_destructive_execution_defaults_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.destructive_execution_mode, "disabled")

    def test_invalid_mode_rejected(self):
        with patch.dict(os.environ, {"MCP_DESTRUCTIVE_EXECUTION_MODE": "maybe"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
