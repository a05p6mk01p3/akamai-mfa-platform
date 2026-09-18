from __future__ import annotations

from dataclasses import dataclass
import os


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável obrigatória não definida: {name}")
    return value


def _enum_env(name: str, default: str, allowed: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in allowed:
        raise ConfigurationError(
            f"{name} inválido: {value!r}; permitidos: {', '.join(sorted(allowed))}"
        )
    return value


@dataclass(frozen=True)
class Settings:
    akamai_host: str
    client_token: str
    client_secret: str
    access_token: str
    contract_id: str
    directory_id: str
    connect_timeout: float
    read_timeout: float
    log_level: str

    database_url: str | None
    operation_ttl_seconds: int
    safe_ref_ttl_seconds: int

    execution_backend: str
    simulation_primitive_outcome: str
    simulation_postcheck_outcome: str

    @property
    def base_url(self) -> str:
        return f"https://{self.akamai_host}"

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def execution_framework_enabled(self) -> bool:
        return self.execution_backend in {"simulation", "live"}

    @property
    def destructive_operations_enabled(self) -> bool:
        # A single operator-facing live gate enables the destructive framework.
        # Domain separation remains enforced by the persisted operation type and
        # its domain-specific execution adapter.
        return self.execution_backend == "live"

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL", "").strip() or None
        return cls(
            akamai_host=_required("AKAMAI_HOST").removeprefix("https://").rstrip("/"),
            client_token=_required("AKAMAI_CLIENT_TOKEN"),
            client_secret=_required("AKAMAI_CLIENT_SECRET"),
            access_token=_required("AKAMAI_ACCESS_TOKEN"),
            contract_id=_required("AKAMAI_CONTRACT_ID"),
            directory_id=_required("AKAMAI_DIRECTORY_ID"),
            connect_timeout=float(os.getenv("AKAMAI_CONNECT_TIMEOUT", "5")),
            read_timeout=float(os.getenv("AKAMAI_READ_TIMEOUT", "15")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            database_url=database_url,
            operation_ttl_seconds=max(60, int(os.getenv("OPERATION_TTL_SECONDS", "300"))),
            safe_ref_ttl_seconds=max(60, int(os.getenv("SAFE_REF_TTL_SECONDS", "300"))),
            execution_backend=_enum_env(
                "EXECUTION_BACKEND",
                "disabled",
                {"disabled", "simulation", "live"},
            ),
            simulation_primitive_outcome=_enum_env(
                "SIMULATION_PRIMITIVE_OUTCOME",
                "expected",
                {"expected", "ambiguous", "failed"},
            ),
            simulation_postcheck_outcome=_enum_env(
                "SIMULATION_POSTCHECK_OUTCOME",
                "expected",
                {"expected", "target_remains", "inconclusive", "wrong_state"},
            ),
        )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise ConfigurationError("Variável obrigatória não definida: DATABASE_URL")
        return self.database_url
