from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .context import ApiRequestContext


class BackendError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


class MfaApiClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        *,
        context: ApiRequestContext,
        require_interaction: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        context_headers = (
            context.destructive_context_headers()
            if require_interaction
            else context.headers()
        )
        headers.update(context_headers)
        try:
            # MCP -> API remains on the private Podman network; never inherit
            # host proxies for this internal hop.
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                trust_env=False,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers=headers,
                    **kwargs,
                )
        except httpx.TimeoutException as exc:
            raise BackendError(
                "timeout ao chamar a API interna de MFA",
                code="backend_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(
                "falha de comunicação com a API interna de MFA",
                code="backend_connection_error",
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.is_success:
            if not isinstance(body, dict):
                raise BackendError(
                    "API interna retornou resposta inesperada",
                    status_code=response.status_code,
                )
            return body

        if isinstance(body, dict):
            message = str(body.get("message") or body.get("detail") or "API interna retornou erro")
            code = body.get("code")
            request_id = body.get("request_id")
        else:
            message = "API interna retornou erro"
            code = None
            request_id = None

        raise BackendError(
            message,
            status_code=response.status_code,
            code=str(code) if code is not None else None,
            request_id=str(request_id) if request_id is not None else None,
        )

    async def search_eaa_user(
        self,
        query: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/eaa/users/search",
            context=context,
            params={"q": query},
        )

    async def get_akamai_mfa_status(
        self,
        user_ref: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        encoded_ref = quote(user_ref, safe="")
        return await self._request(
            "GET",
            f"/v2/akamai-mfa/users/{encoded_ref}/status",
            context=context,
        )

    async def prepare_eaa_otp_reset(
        self,
        user_ref: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v2/eaa-native-mfa/otp-reset/prepare",
            context=context,
            require_interaction=True,
            json={"user_ref": user_ref},
        )

    async def prepare_akamai_mfa_device_reset(
        self,
        user_ref: str,
        device_ref: str | None,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"user_ref": user_ref}
        if device_ref is not None:
            payload["device_ref"] = device_ref
        return await self._request(
            "POST",
            "/v2/akamai-mfa/device-reset/prepare",
            context=context,
            require_interaction=True,
            json=payload,
        )

    async def prepare_retry(
        self,
        parent_operation_id: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        encoded = quote(parent_operation_id, safe="")
        return await self._request(
            "POST",
            f"/v2/operations/{encoded}/retry/prepare",
            context=context,
            require_interaction=True,
        )

    async def get_operation_status(
        self,
        operation_id: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        encoded = quote(operation_id, safe="")
        return await self._request(
            "GET",
            f"/v2/operations/{encoded}",
            context=context,
        )

    async def confirm_operation(
        self,
        operation_id: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        encoded = quote(operation_id, safe="")
        return await self._request(
            "POST",
            f"/v2/operations/{encoded}/confirm",
            context=context,
            require_interaction=True,
        )

    async def execute_operation(
        self,
        operation_id: str,
        *,
        context: ApiRequestContext,
    ) -> dict[str, Any]:
        encoded = quote(operation_id, safe="")
        return await self._request(
            "POST",
            f"/v2/operations/{encoded}/execute",
            context=context,
        )

