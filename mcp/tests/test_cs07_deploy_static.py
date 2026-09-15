from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUADLET = (ROOT / "deploy" / "akamai-mfa-mcp-v2.container.example").read_text()
ENV = (ROOT / "deploy" / "akamai-mfa-mcp-v2.env.example").read_text()
WRAPPER = (ROOT / "deploy" / "librechat-cs07-entrypoint.sh").read_text()
YAML = (ROOT / "deploy" / "librechat-mcp-v2.yaml.snippet").read_text()
CHANGESET = (ROOT / "CHANGESET-07.md").read_text()


class Cs07DeployStaticTests(unittest.TestCase):
    def test_quadlet_has_both_networks(self):
        self.assertIn("Network=akamai-mfa-net", QUADLET)
        self.assertIn("Network=librechat-net", QUADLET)

    def test_quadlet_has_deterministic_dns(self):
        self.assertIn("DNS=10.89.0.1", QUADLET)

    def test_quadlet_has_no_host_publication(self):
        self.assertNotIn("PublishPort=", QUADLET)
        self.assertNotIn("--publish", QUADLET)
        self.assertNotIn(" -p ", QUADLET)

    def test_quadlet_uses_secret_file(self):
        self.assertIn("Secret=akamai-mfa-mcp-ingress-token", QUADLET)
        self.assertIn("target=akamai-mfa-mcp-ingress-token", QUADLET)

    def test_env_keeps_destructive_execution_disabled(self):
        self.assertIn("MCP_DESTRUCTIVE_EXECUTION_MODE=disabled", ENV)

    def test_env_requires_request_bound_context(self):
        self.assertIn("MCP_TRUSTED_CONTEXT_MODE=request_headers", ENV)
        self.assertIn("MCP_INTERACTION_ATTESTATION_MODE=request_header", ENV)
        self.assertIn("MCP_TRUSTED_INGRESS_MODE=shared_secret", ENV)

    def test_env_does_not_embed_ingress_secret_value(self):
        self.assertNotIn("MCP_TRUSTED_INGRESS_SECRET=", ENV)
        self.assertIn("MCP_TRUSTED_INGRESS_SECRET_FILE=", ENV)

    def test_wrapper_reads_secret_file_without_echoing_value(self):
        self.assertIn("/run/secrets/akamai-mfa-mcp-ingress-token", WRAPPER)
        self.assertNotIn("echo \"$AKAMAI_MFA_MCP_INGRESS_TOKEN\"", WRAPPER)
        self.assertIn("export AKAMAI_MFA_MCP_INGRESS_TOKEN", WRAPPER)

    def test_librechat_uses_canonical_hostname_and_runtime_headers(self):
        self.assertIn("http://akamai-mfa-mcp-v2:9000/mcp", YAML)
        self.assertIn("${AKAMAI_MFA_MCP_INGRESS_TOKEN}", YAML)
        self.assertIn("{{LIBRECHAT_USER_ID}}", YAML)
        self.assertIn("{{LIBRECHAT_BODY_CONVERSATIONID}}", YAML)
        self.assertIn("{{LIBRECHAT_BODY_MESSAGEID}}", YAML)

    def test_podman_49_dropin_limitation_is_documented(self):
        self.assertIn("Podman 4.9.4", CHANGESET)
        self.assertIn("source `.container` file", CHANGESET)


if __name__ == "__main__":
    unittest.main()
