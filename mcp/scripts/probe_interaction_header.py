from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.probe_result import content_block_types, decode_call_tool_payload


URL = os.getenv("MCP_PROBE_URL", "http://127.0.0.1:9000/mcp")
HEADER = os.getenv("MCP_INTERACTION_HEADER_NAME", "X-MFA-Interaction")
PROBE_USER_REF = "usr_00000000000000000000"


async def one(label: str, headers: dict[str, str]) -> dict[str, Any] | None:
    async with httpx2.AsyncClient(headers=headers) as http_client:
        transport = streamable_http_client(
            URL,
            http_client=http_client,
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            tool_dump = [
                tool.model_dump(by_alias=True)
                for tool in tools.tools
            ]
            target = next(
                item for item in tool_dump
                if item["name"] == "prepare_eaa_otp_reset"
            )
            properties = (
                target.get("inputSchema", {})
                .get("properties", {})
            )
            print(
                json.dumps(
                    {
                        "label": label,
                        "public_properties": sorted(properties),
                        "contains_ctx": "ctx" in properties,
                        "contains_interaction_ref": (
                            "interaction_ref" in properties
                        ),
                    },
                    ensure_ascii=False,
                )
            )

            result = await client.call_tool(
                "prepare_eaa_otp_reset",
                {"user_ref": PROBE_USER_REF},
            )
            payload = decode_call_tool_payload(result)
            print(
                json.dumps(
                    {
                        "label": label,
                        "is_error": bool(getattr(result, "is_error", False)),
                        "content_block_types": content_block_types(result),
                        "structured_content_present": isinstance(
                            getattr(result, "structured_content", None),
                            dict,
                        ),
                        "result": payload,
                    },
                    ensure_ascii=False,
                )
            )
            return payload


async def main() -> None:
    without = await one("without_header", {})
    with_header = await one(
        "with_header",
        {HEADER: "cs02-runtime-interaction-001"},
    )

    assert without is not None, "without_header payload could not be decoded"
    assert with_header is not None, "with_header payload could not be decoded"
    assert without.get("code") == "interaction_context_unavailable", without
    assert with_header.get("code") == "not_available_in_cs02", with_header
    print("PROBE_OK")


if __name__ == "__main__":
    asyncio.run(main())
