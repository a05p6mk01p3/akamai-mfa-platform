import os
import unittest
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.database import Database
from app.operations.repository import (
    OperationConflict,
    OperationContextMismatch,
    OperationExpired,
    OperationInteractionReuse,
    OperationRepository,
    OperationStateConflict,
)
from app.references.repository import SafeReferenceRepository
from app.references.models import ReferenceType


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL not configured")
class PostgreSqlRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
        settings = Settings.from_env()
        self.db = Database(settings)
        self.ops = OperationRepository(self.db, settings)
        self.refs = SafeReferenceRepository(self.db, settings)
        self.actor = {"actor": "internal-mcp"}
        self.session = {"session": "test"}

    def prepared(self, interaction="turn-1"):
        return self.ops.create_prepared(
            operation_type="TEST_ONLY",
            domain="test",
            actor_context=self.actor,
            session_context=self.session,
            prepared_interaction_ref=interaction,
            target_identity={"username": "u"},
            destructive_target=None,
            prepared_snapshot={},
        )

    def test_operation_confirmation_is_single_consumption_for_confirm_stage(self):
        op = self.prepared()
        confirmed = self.ops.confirm(
            op.operation_id,
            actor_context=self.actor,
            session_context=self.session,
            confirmation_interaction_ref="turn-2",
        )
        self.assertEqual(confirmed.status.value, "CONFIRMED")

        with self.assertRaises(OperationStateConflict):
            self.ops.confirm(
                op.operation_id,
                actor_context=self.actor,
                session_context=self.session,
                confirmation_interaction_ref="turn-3",
            )

    def test_execution_claim_is_still_single_consumption_in_repository(self):
        op = self.prepared()
        self.ops.confirm(
            op.operation_id,
            actor_context=self.actor,
            session_context=self.session,
            confirmation_interaction_ref="turn-2",
        )
        executing = self.ops.claim_execution(
            op.operation_id,
            actor_context=self.actor,
            session_context=self.session,
        )
        self.assertEqual(executing.status.value, "EXECUTING")
        with self.assertRaises(OperationConflict):
            self.ops.claim_execution(
                op.operation_id,
                actor_context=self.actor,
                session_context=self.session,
            )

    def test_same_interaction_cannot_confirm(self):
        op = self.prepared(interaction="turn-same")
        with self.assertRaises(OperationInteractionReuse):
            self.ops.confirm(
                op.operation_id,
                actor_context=self.actor,
                session_context=self.session,
                confirmation_interaction_ref="turn-same",
            )
        current = self.ops.get(op.operation_id)
        self.assertEqual(current.status.value, "PREPARED")

    def test_wrong_context_cannot_confirm(self):
        op = self.prepared()
        with self.assertRaises(OperationContextMismatch):
            self.ops.confirm(
                op.operation_id,
                actor_context=self.actor,
                session_context={"session": "other"},
                confirmation_interaction_ref="turn-2",
            )
        current = self.ops.get(op.operation_id)
        self.assertEqual(current.status.value, "PREPARED")

    def test_expired_prepare_transitions_to_expired_on_confirmation_attempt(self):
        op = self.prepared()
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE operations SET expires_at=%s WHERE operation_id=%s",
                    (datetime.now(timezone.utc) - timedelta(seconds=1), op.operation_id),
                )
            conn.commit()

        with self.assertRaises(OperationExpired):
            self.ops.confirm(
                op.operation_id,
                actor_context=self.actor,
                session_context=self.session,
                confirmation_interaction_ref="turn-2",
            )

        current = self.ops.get(op.operation_id)
        self.assertEqual(current.status.value, "EXPIRED")
        self.assertEqual(current.outcome_code, "operation_expired")

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS n
                    FROM operation_events
                    WHERE operation_id=%s
                      AND event_type='OPERATION_EXPIRED'
                      AND from_state='PREPARED'
                      AND to_state='EXPIRED'
                    """,
                    (op.operation_id,),
                )
                row = cur.fetchone()
        self.assertEqual(row["n"], 1)

    def test_confirmation_event_is_written(self):
        op = self.prepared()
        self.ops.confirm(
            op.operation_id,
            actor_context=self.actor,
            session_context=self.session,
            confirmation_interaction_ref="turn-2",
        )
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS n
                    FROM operation_events
                    WHERE operation_id=%s
                      AND event_type='CONFIRMATION_ACCEPTED'
                      AND from_state='PREPARED'
                      AND to_state='CONFIRMED'
                    """,
                    (op.operation_id,),
                )
                row = cur.fetchone()
        self.assertEqual(row["n"], 1)

    def test_safe_reference_is_context_bound(self):
        ref = self.refs.issue(
            reference_type=ReferenceType.USER,
            domain="identity",
            actor_context=self.actor,
            session_context=self.session,
            target_identity={"username": "u"},
            internal_target={"user_id": "internal"},
        )
        resolved = self.refs.resolve(
            ref.reference_id,
            expected_type=ReferenceType.USER,
            expected_domain="identity",
            actor_context=self.actor,
            session_context=self.session,
        )
        self.assertEqual(resolved.internal_target["user_id"], "internal")


if __name__ == "__main__":
    unittest.main()
