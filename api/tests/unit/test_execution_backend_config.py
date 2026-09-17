import os
import unittest
from unittest.mock import patch

from app.config import ConfigurationError, Settings


BASE_ENV = {
    "AKAMAI_HOST": "example.luna.akamaiapis.net",
    "AKAMAI_CLIENT_TOKEN": "token",
    "AKAMAI_CLIENT_SECRET": "secret",
    "AKAMAI_ACCESS_TOKEN": "access",
    "AKAMAI_CONTRACT_ID": "contract",
    "AKAMAI_DIRECTORY_ID": "directory",
}


class ExecutionBackendConfigTests(unittest.TestCase):
    def settings_for(self, backend):
        env = {**BASE_ENV, "EXECUTION_BACKEND": backend}
        with patch.dict(os.environ, env, clear=True):
            return Settings.from_env()

    def test_live_is_the_single_destructive_api_mode(self):
        settings = self.settings_for("live")
        self.assertTrue(settings.execution_framework_enabled)
        self.assertTrue(settings.destructive_operations_enabled)

    def test_simulation_remains_non_destructive(self):
        settings = self.settings_for("simulation")
        self.assertTrue(settings.execution_framework_enabled)
        self.assertFalse(settings.destructive_operations_enabled)

    def test_disabled_remains_fail_closed(self):
        settings = self.settings_for("disabled")
        self.assertFalse(settings.execution_framework_enabled)
        self.assertFalse(settings.destructive_operations_enabled)

    def test_legacy_eaa_mode_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            self.settings_for("eaa_validation")

    def test_legacy_akamai_mfa_mode_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            self.settings_for("akamai_mfa_validation")


if __name__ == "__main__":
    unittest.main()
