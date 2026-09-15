#!/usr/bin/env python3
"""Read-only CS07 smoke probe.

Run inside the MCP container. It reads the mounted ingress secret, invokes only
search_eaa_user, and prints status/count without dumping candidate identity data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def decode(result):
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


async def run(args) -> int:
    secret = Path(args.secret_file).read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError("trusted ingress secret is empty")

    headers = {
        "X-MFA-Ingress-Token": secret,
        "X-MFA-Actor": args.actor,
        "X-MFA-Session": args.session,
        "X-MFA-Interaction": args.interaction,
    }
    http_client = httpx.AsyncClient(headers=headers)
    transport = streamable_http_client(args.url, http_client=http_client)
    async with http_client:
        async with Client(transport) as client:
            result = decode(
                await client.call_tool("search_eaa_user", {"query": args.query})
            )
    if not result:
        print("status=invalid_result")
        return 2
    print(f"status={result.get('status')}")
    print(f"count={result.get('count')}")
    return 0 if result.get("status") in {"found", "ambiguous", "not_found"} else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:9000/mcp")
    parser.add_argument(
        "--secret-file",
        default="/run/secrets/akamai-mfa-mcp-ingress-token",
    )
    parser.add_argument("--actor", default="cs07-smoke-actor")
    parser.add_argument("--session", default="cs07-smoke-session")
    parser.add_argument("--interaction", default="cs07-smoke-interaction")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
