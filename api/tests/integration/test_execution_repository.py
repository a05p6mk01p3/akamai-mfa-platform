import os
import unittest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from app.config import Settings
from app.database import Database
from app.operations.models import OperationStatus
from app.operations.repository import (
    OperationExpired,
    OperationRepository,
    OperationStateConflict,
)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL not configured")
class ExecutionRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
        self.settings = Settings.from_env()
        self.db = Database(self.settings)
        self.actor = {"actor": "exec-test"}
        self.session = {"session": "exec-session"}

    def repo(self):
        return OperationRepository(Database(self.settings), self.settings)

    def confirmed(self):
        repo = self.repo()
        op = repo.create_prepared(
            operation_type="TEST_EXECUTION",
            domain="test",
            actor_context=self.actor,
            session_context=self.session,
            prepared_interaction_ref="turn-1",
            target_identity={"username": "u"},
            destructive_target={"opaque_internal": "secret"},
            prepared_snapshot={},
        )
        repo.confirm(
            op.operation_id,
            actor_context=self.actor,
            session_context=self.session,
            confirmation_interaction_ref="turn-2",
        )
        return op.operation_id

    def test_concurrent_execution_claim_has_exactly_one_winner(self):
        operation_id = self.confirmed()

        def claim():
            try:
                return self.repo().claim_execution(
                    operation_id,
                    actor_context=self.actor,
                    session_context=self.session,
                ).status.value
            except OperationStateConflict:
                return "REJECTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))

        self.assertEqual(results.count("EXECUTING"), 1)
        self.assertEqual(results.count("REJECTED"), 1)

    def test_expired_confirmed_becomes_expired_on_execute_attempt(self):
        operation_id = self.confirmed()
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE operations SET expires_at=%s WHERE operation_id=%s",
                    (datetime.now(timezone.utc) - timedelta(seconds=1), operation_id),
                )
            conn.commit()

        with self.assertRaises(OperationExpired):
            self.repo().claim_execution(
                operation_id,
                actor_context=self.actor,
                session_context=self.session,
            )

        current = self.repo().get(operation_id)
        self.assertEqual(current.status, OperationStatus.EXPIRED)

    def test_transition_and_event_commit_together(self):
        operation_id = self.confirmed()
        repo = self.repo()
        repo.claim_execution(
            operation_id,
            actor_context=self.actor,
            session_context=self.session,
        )
        repo.transition(
            operation_id,
            expected_status=OperationStatus.EXECUTING,
            new_status=OperationStatus.VERIFYING,
            actor_context=self.actor,
            session_context=self.session,
            event_type="POST_CHECK_STARTED",
            outcome_code="test",
            post_check_result={"safe": True},
        )

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      o.status,
                      count(e.event_id) FILTER (
                        WHERE e.event_type='POST_CHECK_STARTED'
                          AND e.from_state='EXECUTING'
                          AND e.to_state='VERIFYING'
                      ) AS events
                    FROM operations o
                    LEFT JOIN operation_events e ON e.operation_id=o.operation_id
                    WHERE o.operation_id=%s
                    GROUP BY o.status
                    """,
                    (operation_id,),
                )
                row = cur.fetchone()

        self.assertEqual(row["status"], "VERIFYING")
        self.assertEqual(row["events"], 1)


if __name__ == "__main__":
    unittest.main()
