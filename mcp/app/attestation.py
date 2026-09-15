from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock

from .context import ApiRequestContext


class PreparedInteractionUnknown(RuntimeError):
    pass


class PreparedInteractionExpired(PreparedInteractionUnknown):
    pass


class PreparedInteractionContextMismatch(RuntimeError):
    pass


class PreparedInteractionLaterRequired(RuntimeError):
    pass


class PreparedInteractionTypeMismatch(RuntimeError):
    pass


class PreparedInteractionAlreadyClaimed(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedInteractionRecord:
    operation_id: str
    operation_type: str
    domain: str
    actor: str
    session: str
    prepared_interaction_ref: str
    expires_at: str | None
    local_state: str = "PREPARED"


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PreparedInteractionRegistry:
    """Process-local MCP correlation and single-claim gate.

    The API remains authoritative for operation lifecycle. The registry fails
    closed after MCP restart because the trusted prepared-interaction
    correlation is no longer available locally.

    Expired records are retained as bounded local tombstones so callers can
    distinguish a known-but-expired operation from an operation whose trusted
    prepared-interaction context is genuinely unavailable.
    """

    def __init__(self, max_entries: int = 2048) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._records: dict[str, PreparedInteractionRecord] = {}
        self._expired: dict[str, PreparedInteractionRecord] = {}
        self._lock = Lock()

    def _remember_expired_locked(
        self,
        record: PreparedInteractionRecord,
    ) -> None:
        self._expired.pop(record.operation_id, None)

        while len(self._expired) >= self.max_entries:
            oldest_operation_id = next(iter(self._expired))
            self._expired.pop(oldest_operation_id, None)

        self._expired[record.operation_id] = record

    def _purge_expired_locked(self, now: datetime) -> None:
        stale = []

        for operation_id, record in self._records.items():
            expiry = _parse_expiry(record.expires_at)
            if expiry is not None and expiry <= now:
                stale.append(operation_id)

        for operation_id in stale:
            record = self._records.pop(operation_id, None)
            if record is not None:
                self._remember_expired_locked(record)

    @staticmethod
    def _validate_context_and_type(
        record: PreparedInteractionRecord,
        *,
        context: ApiRequestContext,
        expected_operation_type: str,
        expected_domain: str,
    ) -> None:
        if record.actor != context.actor or record.session != context.session:
            raise PreparedInteractionContextMismatch(
                "operation_id não pertence ao contexto MCP atual"
            )

        if (
            record.operation_type != expected_operation_type
            or record.domain != expected_domain
        ):
            raise PreparedInteractionTypeMismatch(
                "operation_id não corresponde ao domínio/tipo deste tool"
            )

    def _get_active_record_locked(
        self,
        *,
        operation_id: str,
        context: ApiRequestContext,
        expected_operation_type: str,
        expected_domain: str,
    ) -> PreparedInteractionRecord:
        record = self._records.get(operation_id)

        if record is None:
            expired = self._expired.get(operation_id)

            if expired is not None:
                self._validate_context_and_type(
                    expired,
                    context=context,
                    expected_operation_type=expected_operation_type,
                    expected_domain=expected_domain,
                )
                raise PreparedInteractionExpired(
                    "a operação preparada expirou e não pode mais ser confirmada ou executada"
                )

            raise PreparedInteractionUnknown(
                "correlação de interação preparada não está disponível neste processo MCP"
            )

        return record

    def record(
        self,
        *,
        operation_id: str,
        operation_type: str,
        domain: str,
        context: ApiRequestContext,
        expires_at: str | None,
    ) -> PreparedInteractionRecord:
        if context.interaction_ref is None:
            raise ValueError("prepared interaction is required")

        record = PreparedInteractionRecord(
            operation_id=operation_id,
            operation_type=operation_type,
            domain=domain,
            actor=context.actor,
            session=context.session,
            prepared_interaction_ref=context.interaction_ref,
            expires_at=expires_at,
        )

        with self._lock:
            self._purge_expired_locked(datetime.now(timezone.utc))

            if (
                len(self._records) >= self.max_entries
                and operation_id not in self._records
            ):
                raise RuntimeError("prepared interaction registry is full")

            self._expired.pop(operation_id, None)
            self._records[operation_id] = record

        return record

    @staticmethod
    def _validate_record(
        record: PreparedInteractionRecord,
        *,
        context: ApiRequestContext,
        expected_operation_type: str,
        expected_domain: str,
    ) -> PreparedInteractionRecord:
        PreparedInteractionRegistry._validate_context_and_type(
            record,
            context=context,
            expected_operation_type=expected_operation_type,
            expected_domain=expected_domain,
        )

        if context.interaction_ref is None:
            raise PreparedInteractionLaterRequired(
                "interação humana posterior não está disponível"
            )

        if context.interaction_ref == record.prepared_interaction_ref:
            raise PreparedInteractionLaterRequired(
                "a execução exige uma interação humana posterior ao prepare"
            )

        return record

    def require_later_interaction(
        self,
        *,
        operation_id: str,
        context: ApiRequestContext,
        expected_operation_type: str,
        expected_domain: str,
    ) -> PreparedInteractionRecord:
        with self._lock:
            self._purge_expired_locked(datetime.now(timezone.utc))

            record = self._get_active_record_locked(
                operation_id=operation_id,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
            )

            record = self._validate_record(
                record,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
            )

            if record.local_state != "PREPARED":
                raise PreparedInteractionAlreadyClaimed(
                    "a autorização local desta operação já foi consumida ou está em andamento"
                )

            return record

    def claim_for_reset(
        self,
        *,
        operation_id: str,
        context: ApiRequestContext,
        expected_operation_type: str,
        expected_domain: str,
    ) -> PreparedInteractionRecord:
        with self._lock:
            self._purge_expired_locked(datetime.now(timezone.utc))

            record = self._get_active_record_locked(
                operation_id=operation_id,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
            )

            record = self._validate_record(
                record,
                context=context,
                expected_operation_type=expected_operation_type,
                expected_domain=expected_domain,
            )

            if record.local_state != "PREPARED":
                raise PreparedInteractionAlreadyClaimed(
                    "a autorização local desta operação já foi consumida ou está em andamento"
                )

            claimed = replace(record, local_state="CLAIMED")
            self._records[operation_id] = claimed
            return claimed

    def release_claim(self, operation_id: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is not None and record.local_state == "CLAIMED":
                self._records[operation_id] = replace(
                    record,
                    local_state="PREPARED",
                )

    def mark_terminal(self, operation_id: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is not None:
                self._records[operation_id] = replace(
                    record,
                    local_state="TERMINAL",
                )

    def count(self) -> int:
        with self._lock:
            self._purge_expired_locked(datetime.now(timezone.utc))
            return len(self._records)
