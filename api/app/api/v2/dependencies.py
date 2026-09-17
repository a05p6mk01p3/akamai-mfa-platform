from __future__ import annotations

from functools import lru_cache

from ...clients.akamai_mfa import AkamaiMfaClient
from ...clients.eaa import EaaClient
from ...config import Settings
from ...database import Database
from ...operations.manager import OperationManager
from ...operations.repository import OperationRepository
from ...operations.runtime import build_runtime_execution_adapter
from ...references.repository import SafeReferenceRepository
from ...references.service import SafeReferenceService
from ...services.akamai_mfa import AkamaiMfaService
from ...services.eaa import EaaService


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings.from_env()


@lru_cache(maxsize=1)
def database() -> Database:
    return Database(settings())


def eaa_service() -> EaaService:
    return EaaService(EaaClient(settings()))


def akamai_mfa_service() -> AkamaiMfaService:
    return AkamaiMfaService(AkamaiMfaClient(settings()))


def safe_reference_repository() -> SafeReferenceRepository:
    return SafeReferenceRepository(database(), settings())


def reference_service() -> SafeReferenceService:
    return SafeReferenceService(safe_reference_repository())


def operation_repository() -> OperationRepository:
    return OperationRepository(database(), settings())


def operation_manager() -> OperationManager:
    eaa = eaa_service()
    amfa = akamai_mfa_service()
    return OperationManager(
        operations=operation_repository(),
        references=safe_reference_repository(),
        reference_service=reference_service(),
        eaa_service=eaa,
        akamai_mfa_service=amfa,
        execution_adapter=build_runtime_execution_adapter(
            settings(),
            eaa_service=eaa,
            akamai_mfa_service=amfa,
        ),
    )
