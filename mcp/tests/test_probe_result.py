import unittest
from types import SimpleNamespace

from app.probe_result import content_block_types, decode_call_tool_payload


class ProbeResultTests(unittest.TestCase):
    def test_prefers_structured_content_when_present(self):
        result = SimpleNamespace(
            structured_content={"code": "structured"},
            content=[
                SimpleNamespace(
                    type="text",
                    text='{"code":"text"}',
                )
            ],
        )
        self.assertEqual(
            decode_call_tool_payload(result),
            {"code": "structured"},
        )

    def test_decodes_json_object_from_text_content(self):
        result = SimpleNamespace(
            structured_content=None,
            content=[
                SimpleNamespace(
                    type="text",
                    text='{"status":"error","code":"interaction_context_unavailable"}',
                )
            ],
        )
        self.assertEqual(
            decode_call_tool_payload(result),
            {
                "status": "error",
                "code": "interaction_context_unavailable",
            },
        )

    def test_ignores_non_json_text(self):
        result = SimpleNamespace(
            structured_content=None,
            content=[
                SimpleNamespace(type="text", text="plain text"),
            ],
        )
        self.assertIsNone(decode_call_tool_payload(result))

    def test_reports_content_block_types(self):
        result = SimpleNamespace(
            content=[
                SimpleNamespace(type="text"),
                SimpleNamespace(type="image"),
            ]
        )
        self.assertEqual(
            content_block_types(result),
            ["text", "image"],
        )


if __name__ == "__main__":
    unittest.main()
