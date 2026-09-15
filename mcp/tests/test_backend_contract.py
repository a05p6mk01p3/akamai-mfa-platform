import unittest
from unittest.mock import AsyncMock, patch

from app.backend import MfaApiClient
from app.context import ApiRequestContext


class _Response:
    is_success = True
    status_code = 200
    def __init__(self, body):
        self._body = body
    def json(self):
        return self._body


class _Client:
    def __init__(self, response):
        self.request = AsyncMock(return_value=response)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False


class BackendContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_v2_route_and_context_headers(self):
        fake = _Client(_Response({"status": "not_found", "candidates": []}))
        with patch("app.backend.httpx.AsyncClient", return_value=fake):
            api = MfaApiClient("http://api:8000")
            await api.search_eaa_user(
                "Example User",
                context=ApiRequestContext("actor", "session"),
            )
        fake.request.assert_awaited_once_with(
            "GET",
            "/v2/eaa/users/search",
            headers={"X-MFA-Actor": "actor", "X-MFA-Session": "session"},
            params={"q": "Example User"},
        )

    async def test_status_uses_v2_safe_user_ref_route(self):
        fake = _Client(_Response({"account_present": False, "factors": []}))
        with patch("app.backend.httpx.AsyncClient", return_value=fake):
            api = MfaApiClient("http://api:8000")
            await api.get_akamai_mfa_status(
                "usr_ABCDEFGHIJKLMNOPQRSTUVWX",
                context=ApiRequestContext("actor", "session"),
            )
        args = fake.request.await_args
        self.assertEqual(args.args[0], "GET")
        self.assertTrue(args.args[1].startswith("/v2/akamai-mfa/users/usr_"))
        self.assertEqual(
            args.kwargs["headers"],
            {"X-MFA-Actor": "actor", "X-MFA-Session": "session"},
        )


if __name__ == "__main__":
    unittest.main()



class InteractionHeaderBoundaryTests(unittest.TestCase):
    def test_interaction_attestation_not_sent_on_readonly_context_headers(self):
        from app.context import ApiRequestContext

        context = ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref="interaction-1",
            interaction_source="request_header",
        )
        self.assertEqual(
            context.headers(),
            {
                "X-MFA-Actor": "actor",
                "X-MFA-Session": "session",
            },
        )
        self.assertNotIn("X-MFA-Interaction", context.headers())



class PrepareBackendContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_eaa_prepare_uses_prepare_route_and_interaction_header(self):
        from unittest.mock import AsyncMock, patch
        from app.backend import MfaApiClient
        from app.context import ApiRequestContext

        response = unittest.mock.Mock()
        response.is_success = True
        response.status_code = 200
        response.json.return_value = {"status": "prepared"}

        context = ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref="turn-1",
            interaction_source="request_header",
        )

        with patch("app.backend.httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.request.return_value = response
            client_cls.return_value.__aenter__.return_value = client

            api = MfaApiClient("http://api:8000")
            await api.prepare_eaa_otp_reset("usr_" + "a" * 20, context=context)

            args, kwargs = client.request.await_args
            self.assertEqual(args[:2], ("POST", "/v2/eaa-native-mfa/otp-reset/prepare"))
            self.assertEqual(kwargs["json"], {"user_ref": "usr_" + "a" * 20})
            self.assertEqual(kwargs["headers"]["X-MFA-Actor"], "actor")
            self.assertEqual(kwargs["headers"]["X-MFA-Session"], "session")
            self.assertEqual(kwargs["headers"]["X-MFA-Interaction"], "turn-1")

    async def test_amfa_prepare_uses_device_prepare_route(self):
        from unittest.mock import AsyncMock, patch
        from app.backend import MfaApiClient
        from app.context import ApiRequestContext

        response = unittest.mock.Mock()
        response.is_success = True
        response.status_code = 200
        response.json.return_value = {"status": "prepared"}

        context = ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref="turn-2",
            interaction_source="request_header",
        )

        with patch("app.backend.httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.request.return_value = response
            client_cls.return_value.__aenter__.return_value = client

            api = MfaApiClient("http://api:8000")
            await api.prepare_akamai_mfa_device_reset(
                "usr_" + "a" * 20,
                "dev_" + "b" * 20,
                context=context,
            )

            args, kwargs = client.request.await_args
            self.assertEqual(args[:2], ("POST", "/v2/akamai-mfa/device-reset/prepare"))
            self.assertEqual(
                kwargs["json"],
                {
                    "user_ref": "usr_" + "a" * 20,
                    "device_ref": "dev_" + "b" * 20,
                },
            )
            self.assertEqual(kwargs["headers"]["X-MFA-Interaction"], "turn-2")

    async def test_retry_prepare_has_no_target_override_body(self):
        from unittest.mock import AsyncMock, patch
        from app.backend import MfaApiClient
        from app.context import ApiRequestContext

        response = unittest.mock.Mock()
        response.is_success = True
        response.status_code = 200
        response.json.return_value = {"status": "prepared"}

        context = ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref="turn-3",
            interaction_source="request_header",
        )
        op = "op_" + "c" * 20

        with patch("app.backend.httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.request.return_value = response
            client_cls.return_value.__aenter__.return_value = client

            api = MfaApiClient("http://api:8000")
            await api.prepare_retry(op, context=context)

            args, kwargs = client.request.await_args
            self.assertEqual(args[:2], ("POST", f"/v2/operations/{op}/retry/prepare"))
            self.assertNotIn("json", kwargs)
            self.assertEqual(kwargs["headers"]["X-MFA-Interaction"], "turn-3")



class LifecycleBackendContractTests(unittest.IsolatedAsyncioTestCase):
    def context(self, interaction="turn-2"):
        from app.context import ApiRequestContext
        return ApiRequestContext(
            actor="actor",
            session="session",
            interaction_ref=interaction,
            interaction_source="request_header",
        )

    async def _call(self, method_name):
        from unittest.mock import AsyncMock, patch
        from app.backend import MfaApiClient

        response = unittest.mock.Mock()
        response.is_success = True
        response.status_code = 200
        response.json.return_value = {"ok": True}
        op = "op_" + "c" * 20

        with patch("app.backend.httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.request.return_value = response
            client_cls.return_value.__aenter__.return_value = client
            api = MfaApiClient("http://api:8000")
            await getattr(api, method_name)(op, context=self.context())
            return op, client.request.await_args

    async def test_confirm_sends_interaction_header(self):
        op, call = await self._call("confirm_operation")
        args, kwargs = call
        self.assertEqual(args[:2], ("POST", f"/v2/operations/{op}/confirm"))
        self.assertEqual(kwargs["headers"]["X-MFA-Interaction"], "turn-2")

    async def test_execute_sends_no_interaction_header_or_target(self):
        op, call = await self._call("execute_operation")
        args, kwargs = call
        self.assertEqual(args[:2], ("POST", f"/v2/operations/{op}/execute"))
        self.assertNotIn("X-MFA-Interaction", kwargs["headers"])
        self.assertNotIn("json", kwargs)

    async def test_operation_status_is_observational_get(self):
        op, call = await self._call("get_operation_status")
        args, kwargs = call
        self.assertEqual(args[:2], ("GET", f"/v2/operations/{op}"))
        self.assertNotIn("json", kwargs)
