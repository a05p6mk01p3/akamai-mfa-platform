from __future__ import annotations

import json
from typing import Any


def decode_call_tool_payload(result: Any) -> dict[str, Any] | None:
    """Extract a JSON-object tool payload from CallToolResult.

    Prefer structured_content when the tool declares/returns structured output.
    Otherwise inspect text content blocks, which is the normal model-facing
    representation and may be the only representation present.
    """
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None)
    if not isinstance(content, list):
        return None

    for block in content:
        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if block_type != "text" or not isinstance(text, str):
            continue
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded

    return None


def content_block_types(result: Any) -> list[str]:
    content = getattr(result, "content", None)
    if not isinstance(content, list):
        return []
    return [
        str(getattr(block, "type", type(block).__name__))
        for block in content
    ]
