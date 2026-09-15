from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Mapping

from ..config import Settings
from ..database import Database
from .models import ReferenceType, SafeReference


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


class SafeReferenceError(RuntimeError):
    pass


class SafeReferenceNotFound(SafeReferenceError):
    pass


class SafeReferenceExpired(SafeReferenceError):
    pass


class SafeReferenceContextMismatch(SafeReferenceError):
    pass


class SafeReferenceRepository:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.ttl_seconds = settings.safe_ref_ttl_seconds

    @staticmethod
    def _prefix(reference_type: ReferenceType) -> str:
        return "usr_" if reference_type == ReferenceType.USER else "dev_"

    @classmethod
    def _new_id(cls, reference_type: ReferenceType) -> str:
        return cls._prefix(reference_type) + secrets.token_urlsafe(24)

    def issue(
        self,
        *,
        reference_type: ReferenceType,
        domain: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        target_identity: Mapping[str, Any],
        internal_target: Mapping[str, Any],
    ) -> SafeReference:
        reference_id = self._new_id(reference_type)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)

        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO safe_references (
                        reference_id, reference_type, domain,
                        actor_context, session_context,
                        target_identity, internal_target, expires_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        reference_id,
                        reference_type.value,
                        domain,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                        _jsonb(dict(target_identity)),
                        _jsonb(dict(internal_target)),
                        expires_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return self._row(row)

    @staticmethod
    def _row(row: Mapping[str, Any]) -> SafeReference:
        return SafeReference(
            reference_id=row["reference_id"],
            reference_type=ReferenceType(row["reference_type"]),
            domain=row["domain"],
            actor_context=row["actor_context"],
            session_context=row["session_context"],
            target_identity=row["target_identity"],
            internal_target=row["internal_target"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def resolve(
        self,
        reference_id: str,
        *,
        expected_type: ReferenceType,
        expected_domain: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
    ) -> SafeReference:
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM safe_references
                    WHERE reference_id=%s
                      AND reference_type=%s
                      AND domain=%s
                    """,
                    (reference_id, expected_type.value, expected_domain),
                )
                row = cur.fetchone()

        if row is None:
            raise SafeReferenceNotFound("Referência não encontrada")

        ref = self._row(row)
        if ref.expires_at <= datetime.now(timezone.utc):
            raise SafeReferenceExpired("Referência expirada")
        if dict(ref.actor_context) != dict(actor_context):
            raise SafeReferenceContextMismatch("actor context mismatch")
        if dict(ref.session_context) != dict(session_context):
            raise SafeReferenceContextMismatch("session context mismatch")
        return ref

    def purge_expired(self) -> int:
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM safe_references WHERE expires_at <= now()"
                )
                count = cur.rowcount
            conn.commit()
        return count
