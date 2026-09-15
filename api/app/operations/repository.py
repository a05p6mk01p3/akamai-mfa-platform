from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Mapping, Optional

from ..config import Settings
from ..database import Database
from .models import OperationRecord, OperationStatus


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


class OperationRepositoryError(RuntimeError):
    pass


class OperationNotFound(OperationRepositoryError):
    pass


class OperationConflict(OperationRepositoryError):
    pass


class OperationExpired(OperationConflict):
    pass


class OperationInteractionReuse(OperationConflict):
    pass


class OperationStateConflict(OperationConflict):
    pass


class OperationContextMismatch(OperationRepositoryError):
    pass


class OperationRepository:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.ttl_seconds = settings.operation_ttl_seconds

    @staticmethod
    def _new_id() -> str:
        return "op_" + secrets.token_urlsafe(24)

    @staticmethod
    def _record(row: Mapping[str, Any]) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            parent_operation_id=row["parent_operation_id"],
            operation_type=row["operation_type"],
            domain=row["domain"],
            actor_context=row["actor_context"],
            session_context=row["session_context"],
            prepared_interaction_ref=row["prepared_interaction_ref"],
            target_identity=row["target_identity"],
            destructive_target=row["destructive_target"],
            prepared_snapshot=row["prepared_snapshot"],
            status=OperationStatus(row["status"]),
            prepared_at=row["prepared_at"],
            confirmed_at=row["confirmed_at"],
            execution_started_at=row["execution_started_at"],
            expires_at=row["expires_at"],
            execution_attempts=row["execution_attempts"],
            post_check_result=row["post_check_result"],
            outcome_code=row["outcome_code"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _event(
        cur: Any,
        *,
        operation_id: str,
        event_type: str,
        from_state: str | None,
        to_state: str | None,
        request_id: str | None,
        actor_context: Mapping[str, Any],
        safe_metadata: Mapping[str, Any] | None = None,
        outcome_code: str | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO operation_events (
                operation_id, event_type, from_state, to_state, request_id,
                actor_context, safe_metadata, outcome_code
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                operation_id, event_type, from_state, to_state, request_id,
                _jsonb(dict(actor_context)), _jsonb(dict(safe_metadata or {})), outcome_code,
            ),
        )

    def create_prepared(
        self,
        *,
        operation_type: str,
        domain: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        prepared_interaction_ref: str,
        target_identity: Mapping[str, Any],
        destructive_target: Mapping[str, Any] | None,
        prepared_snapshot: Mapping[str, Any],
        request_id: str | None = None,
        parent_operation_id: str | None = None,
    ) -> OperationRecord:
        if not prepared_interaction_ref:
            raise OperationConflict("prepared interaction reference required")
        operation_id = self._new_id()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)

        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO operations (
                        operation_id, parent_operation_id, operation_type, domain,
                        actor_context, session_context, prepared_interaction_ref,
                        target_identity, destructive_target, prepared_snapshot,
                        status, expires_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PREPARED',%s
                    )
                    RETURNING *
                    """,
                    (
                        operation_id,
                        parent_operation_id,
                        operation_type,
                        domain,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                        prepared_interaction_ref,
                        _jsonb(dict(target_identity)),
                        _jsonb(dict(destructive_target)) if destructive_target is not None else None,
                        _jsonb(dict(prepared_snapshot)),
                        expires_at,
                    ),
                )
                row = cur.fetchone()
                assert row is not None
                self._event(
                    cur,
                    operation_id=operation_id,
                    event_type="OPERATION_PREPARED",
                    from_state=None,
                    to_state="PREPARED",
                    request_id=request_id,
                    actor_context=actor_context,
                    safe_metadata={"domain": domain, "operation_type": operation_type},
                )
            conn.commit()
        return self._record(row)


    def create_retry_child(
        self,
        *,
        parent_operation_id: str,
        operation_type: str,
        domain: str,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        prepared_interaction_ref: str,
        target_identity: Mapping[str, Any],
        destructive_target: Mapping[str, Any] | None,
        prepared_snapshot: Mapping[str, Any],
        request_id: str | None = None,
    ) -> OperationRecord:
        """Atomically create at most one direct retry child for a parent.

        The parent is locked first. It must remain REQUIRES_RECONFIRMATION and
        context-bound to the same actor/session. The parent itself is never
        reactivated or granted new authorization.
        """
        if not prepared_interaction_ref:
            raise OperationConflict("prepared interaction reference required")

        child_operation_id = self._new_id()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)

        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM operations WHERE operation_id=%s FOR UPDATE",
                    (parent_operation_id,),
                )
                parent_row = cur.fetchone()
                if parent_row is None:
                    conn.rollback()
                    raise OperationNotFound("Operação pai não encontrada")

                parent = self._record(parent_row)
                if dict(parent.actor_context) != dict(actor_context):
                    conn.rollback()
                    raise OperationContextMismatch("actor context mismatch")
                if dict(parent.session_context) != dict(session_context):
                    conn.rollback()
                    raise OperationContextMismatch("session context mismatch")
                if parent.status != OperationStatus.REQUIRES_RECONFIRMATION:
                    conn.rollback()
                    raise OperationStateConflict(
                        "retry preparation requires REQUIRES_RECONFIRMATION"
                    )
                if parent.operation_type != operation_type or parent.domain != domain:
                    conn.rollback()
                    raise OperationStateConflict("retry child domain/type mismatch")

                # The parent row lock serializes concurrent retry preparation.
                # A direct parent can produce only one child. Further retries
                # must continue from the newest child in the chain.
                cur.execute(
                    """
                    SELECT operation_id
                    FROM operations
                    WHERE parent_operation_id=%s
                    ORDER BY created_at, operation_id
                    LIMIT 1
                    """,
                    (parent_operation_id,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    conn.rollback()
                    raise OperationStateConflict(
                        "retry child already prepared for this parent"
                    )

                cur.execute(
                    """
                    INSERT INTO operations (
                        operation_id, parent_operation_id, operation_type, domain,
                        actor_context, session_context, prepared_interaction_ref,
                        target_identity, destructive_target, prepared_snapshot,
                        status, expires_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PREPARED',%s
                    )
                    RETURNING *
                    """,
                    (
                        child_operation_id,
                        parent_operation_id,
                        operation_type,
                        domain,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                        prepared_interaction_ref,
                        _jsonb(dict(target_identity)),
                        _jsonb(dict(destructive_target))
                        if destructive_target is not None
                        else None,
                        _jsonb(dict(prepared_snapshot)),
                        expires_at,
                    ),
                )
                child_row = cur.fetchone()
                assert child_row is not None

                self._event(
                    cur,
                    operation_id=child_operation_id,
                    event_type="RETRY_CHILD_PREPARED",
                    from_state=None,
                    to_state="PREPARED",
                    request_id=request_id,
                    actor_context=actor_context,
                    safe_metadata={
                        "domain": domain,
                        "operation_type": operation_type,
                        "retry_child": True,
                    },
                )
                self._event(
                    cur,
                    operation_id=parent_operation_id,
                    event_type="RETRY_CHILD_LINKED",
                    from_state="REQUIRES_RECONFIRMATION",
                    to_state="REQUIRES_RECONFIRMATION",
                    request_id=request_id,
                    actor_context=actor_context,
                    safe_metadata={
                        "child_operation_id": child_operation_id,
                    },
                )
            conn.commit()

        return self._record(child_row)

    def get(
        self,
        operation_id: str,
        *,
        actor_context: Mapping[str, Any] | None = None,
        session_context: Mapping[str, Any] | None = None,
    ) -> OperationRecord:
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE operation_id=%s", (operation_id,))
                row = cur.fetchone()
        if row is None:
            raise OperationNotFound("Operação não encontrada")
        record = self._record(row)
        if actor_context is not None and dict(record.actor_context) != dict(actor_context):
            raise OperationContextMismatch("actor context mismatch")
        if session_context is not None and dict(record.session_context) != dict(session_context):
            raise OperationContextMismatch("session context mismatch")
        return record

    def expire_due(self) -> int:
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH candidates AS (
                        SELECT operation_id, status AS from_state
                        FROM operations
                        WHERE status IN ('PREPARED','CONFIRMED')
                          AND expires_at <= now()
                        FOR UPDATE
                    ), expired AS (
                        UPDATE operations o
                        SET status='EXPIRED', updated_at=now(), outcome_code='operation_expired'
                        FROM candidates c
                        WHERE o.operation_id=c.operation_id
                        RETURNING o.operation_id, o.actor_context, c.from_state
                    )
                    SELECT operation_id, actor_context, from_state FROM expired
                    """
                )
                rows = cur.fetchall()
                for row in rows:
                    self._event(
                        cur,
                        operation_id=row["operation_id"],
                        event_type="OPERATION_EXPIRED",
                        from_state=row["from_state"],
                        to_state="EXPIRED",
                        request_id=None,
                        actor_context=row["actor_context"],
                        outcome_code="operation_expired",
                    )
            conn.commit()
        return len(rows)

    def confirm(
        self,
        operation_id: str,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        confirmation_interaction_ref: str,
        request_id: str | None = None,
    ) -> OperationRecord:
        """Transition PREPARED -> CONFIRMED on a distinct later interaction.

        This method is fail-closed:
        - operation must exist;
        - actor/session must match exactly;
        - only PREPARED can be confirmed;
        - expired PREPARED becomes EXPIRED transactionally;
        - the prepare interaction cannot confirm the operation;
        - replay cannot reconfirm an already-confirmed operation.

        No upstream mutation is performed here.
        """
        if not confirmation_interaction_ref:
            raise OperationInteractionReuse("confirmation interaction reference required")

        pending_error: OperationRepositoryError | None = None
        confirmed_row = None

        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM operations WHERE operation_id=%s FOR UPDATE",
                    (operation_id,),
                )
                row = cur.fetchone()

                if row is None:
                    conn.rollback()
                    raise OperationNotFound("Operação não encontrada")

                record = self._record(row)

                if dict(record.actor_context) != dict(actor_context):
                    conn.rollback()
                    raise OperationContextMismatch("actor context mismatch")
                if dict(record.session_context) != dict(session_context):
                    conn.rollback()
                    raise OperationContextMismatch("session context mismatch")

                if record.status == OperationStatus.PREPARED and record.expires_at <= datetime.now(timezone.utc):
                    cur.execute(
                        """
                        UPDATE operations
                        SET status='EXPIRED',
                            updated_at=now(),
                            outcome_code='operation_expired'
                        WHERE operation_id=%s
                          AND status='PREPARED'
                        RETURNING *
                        """,
                        (operation_id,),
                    )
                    expired_row = cur.fetchone()
                    if expired_row is None:
                        conn.rollback()
                        raise OperationStateConflict("operation state changed concurrently")
                    self._event(
                        cur,
                        operation_id=operation_id,
                        event_type="OPERATION_EXPIRED",
                        from_state="PREPARED",
                        to_state="EXPIRED",
                        request_id=request_id,
                        actor_context=actor_context,
                        outcome_code="operation_expired",
                    )
                    conn.commit()
                    pending_error = OperationExpired("Operação expirada")

                elif record.status != OperationStatus.PREPARED:
                    conn.rollback()
                    raise OperationStateConflict(
                        f"Operação não pode ser confirmada no estado {record.status.value}"
                    )

                elif record.prepared_interaction_ref == confirmation_interaction_ref:
                    conn.rollback()
                    raise OperationInteractionReuse(
                        "A confirmação deve ocorrer em interação posterior ao prepare"
                    )

                else:
                    cur.execute(
                        """
                        UPDATE operations
                        SET status='CONFIRMED',
                            confirmed_at=now(),
                            updated_at=now()
                        WHERE operation_id=%s
                          AND status='PREPARED'
                        RETURNING *
                        """,
                        (operation_id,),
                    )
                    confirmed_row = cur.fetchone()
                    if confirmed_row is None:
                        conn.rollback()
                        raise OperationStateConflict("operation state changed concurrently")

                    self._event(
                        cur,
                        operation_id=operation_id,
                        event_type="CONFIRMATION_ACCEPTED",
                        from_state="PREPARED",
                        to_state="CONFIRMED",
                        request_id=request_id,
                        actor_context=actor_context,
                        safe_metadata={
                            "interaction_distinct_from_prepare": True,
                        },
                    )
                    conn.commit()

        if pending_error is not None:
            raise pending_error

        assert confirmed_row is not None
        return self._record(confirmed_row)

    def claim_execution(
        self,
        operation_id: str,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        request_id: str | None = None,
    ) -> OperationRecord:
        """Atomically consume CONFIRMED authorization.

        TTL authorizes starting execution only. Once successfully claimed,
        expiration does not interrupt EXECUTING.
        """
        pending_error: OperationRepositoryError | None = None
        claimed_row = None

        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operations
                    SET status='EXECUTING',
                        execution_started_at=now(),
                        execution_attempts=execution_attempts + 1,
                        updated_at=now()
                    WHERE operation_id=%s
                      AND status='CONFIRMED'
                      AND expires_at > now()
                      AND actor_context=%s
                      AND session_context=%s
                    RETURNING *
                    """,
                    (
                        operation_id,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                    ),
                )
                claimed_row = cur.fetchone()

                if claimed_row is not None:
                    self._event(
                        cur,
                        operation_id=operation_id,
                        event_type="EXECUTION_CLAIMED",
                        from_state="CONFIRMED",
                        to_state="EXECUTING",
                        request_id=request_id,
                        actor_context=actor_context,
                    )
                    conn.commit()
                else:
                    cur.execute(
                        "SELECT * FROM operations WHERE operation_id=%s FOR UPDATE",
                        (operation_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        raise OperationNotFound("Operação não encontrada")

                    record = self._record(row)
                    if dict(record.actor_context) != dict(actor_context):
                        conn.rollback()
                        raise OperationContextMismatch("actor context mismatch")
                    if dict(record.session_context) != dict(session_context):
                        conn.rollback()
                        raise OperationContextMismatch("session context mismatch")

                    if (
                        record.status == OperationStatus.CONFIRMED
                        and record.expires_at <= datetime.now(timezone.utc)
                    ):
                        cur.execute(
                            """
                            UPDATE operations
                            SET status='EXPIRED',
                                updated_at=now(),
                                outcome_code='operation_expired'
                            WHERE operation_id=%s
                              AND status='CONFIRMED'
                            RETURNING *
                            """,
                            (operation_id,),
                        )
                        expired_row = cur.fetchone()
                        if expired_row is None:
                            conn.rollback()
                            raise OperationStateConflict("operation state changed concurrently")
                        self._event(
                            cur,
                            operation_id=operation_id,
                            event_type="OPERATION_EXPIRED",
                            from_state="CONFIRMED",
                            to_state="EXPIRED",
                            request_id=request_id,
                            actor_context=actor_context,
                            outcome_code="operation_expired",
                        )
                        conn.commit()
                        pending_error = OperationExpired("Operação expirada")
                    else:
                        conn.rollback()
                        raise OperationStateConflict(
                            f"Operação não pode iniciar execução no estado {record.status.value}"
                        )

        if pending_error is not None:
            raise pending_error

        assert claimed_row is not None
        return self._record(claimed_row)

    def transition(
        self,
        operation_id: str,
        *,
        expected_status: OperationStatus,
        new_status: OperationStatus,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        event_type: str,
        request_id: str | None = None,
        outcome_code: str | None = None,
        post_check_result: Mapping[str, Any] | None = None,
        last_error: Mapping[str, Any] | None = None,
        safe_metadata: Mapping[str, Any] | None = None,
    ) -> OperationRecord:
        """CAS-like single-state transition with event in the same transaction."""
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operations
                    SET status=%s,
                        updated_at=now(),
                        outcome_code=%s,
                        post_check_result=%s,
                        last_error=%s
                    WHERE operation_id=%s
                      AND status=%s
                      AND actor_context=%s
                      AND session_context=%s
                    RETURNING *
                    """,
                    (
                        new_status.value,
                        outcome_code,
                        _jsonb(dict(post_check_result)) if post_check_result is not None else None,
                        _jsonb(dict(last_error)) if last_error is not None else None,
                        operation_id,
                        expected_status.value,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    current = self.get(operation_id)
                    if dict(current.actor_context) != dict(actor_context):
                        raise OperationContextMismatch("actor context mismatch")
                    if dict(current.session_context) != dict(session_context):
                        raise OperationContextMismatch("session context mismatch")
                    raise OperationStateConflict(
                        f"expected {expected_status.value}, found {current.status.value}"
                    )

                self._event(
                    cur,
                    operation_id=operation_id,
                    event_type=event_type,
                    from_state=expected_status.value,
                    to_state=new_status.value,
                    request_id=request_id,
                    actor_context=actor_context,
                    safe_metadata=safe_metadata,
                    outcome_code=outcome_code,
                )
            conn.commit()
        return self._record(row)

    def record_verification_observation(
        self,
        operation_id: str,
        *,
        actor_context: Mapping[str, Any],
        session_context: Mapping[str, Any],
        post_check_result: Mapping[str, Any],
        outcome_code: str,
        request_id: str | None = None,
    ) -> OperationRecord:
        """Update a VERIFYING observation without changing state or mutating upstream."""
        with self.database.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operations
                    SET updated_at=now(),
                        outcome_code=%s,
                        post_check_result=%s
                    WHERE operation_id=%s
                      AND status='VERIFYING'
                      AND actor_context=%s
                      AND session_context=%s
                    RETURNING *
                    """,
                    (
                        outcome_code,
                        _jsonb(dict(post_check_result)),
                        operation_id,
                        _jsonb(dict(actor_context)),
                        _jsonb(dict(session_context)),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise OperationStateConflict("operation is not VERIFYING")
                self._event(
                    cur,
                    operation_id=operation_id,
                    event_type="VERIFICATION_INCONCLUSIVE",
                    from_state="VERIFYING",
                    to_state="VERIFYING",
                    request_id=request_id,
                    actor_context=actor_context,
                    outcome_code=outcome_code,
                )
            conn.commit()
        return self._record(row)
