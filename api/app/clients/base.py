from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import requests
from ..config import Settings
from ..errors import UpstreamError, UpstreamTimeout


class EdgeGridHttpClient:
    """Shared read-only HTTP mechanics for Akamai clients.

    Domain paths and parsing remain in the specific EAA/Akamai MFA clients.
    No retry policy is implemented here.
    """

    def __init__(self, settings: Settings) -> None:
        from akamai.edgegrid import EdgeGridAuth

        self.settings = settings
        self.session = requests.Session()
        self.session.trust_env = True
        self.session.headers.update({"Accept": "application/json"})
        self.session.auth = EdgeGridAuth(
            client_token=settings.client_token,
            client_secret=settings.client_secret,
            access_token=settings.access_token,
        )
        self.timeout = (settings.connect_timeout, settings.read_timeout)

    def _url(self, path: str) -> str:
        return f"{self.settings.base_url}{path}"

    @staticmethod
    def safe_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            text = response.text.strip()
            return text[:2000] if text else None

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(
                method,
                self._url(path),
                timeout=self.timeout,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise UpstreamTimeout("Timeout ao consultar a API Akamai") from exc
        except requests.RequestException as exc:
            raise UpstreamError("Falha de comunicação com a API Akamai") from exc

        if response.status_code >= 400:
            raise UpstreamError(
                f"Akamai retornou HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=self.safe_json(response),
            )
        return response

    @staticmethod
    def objects(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("objects", "users", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    @staticmethod
    def first(item: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
        for key in keys:
            value = item.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                normalized = str(value).strip()
                if normalized:
                    return normalized
        return None
