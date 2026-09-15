import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.config import Settings
from app.database import Database
from app.operations.models import OperationStatus
from app.operations.repository import (
    OperationRepository,
    OperationStateConflict,
)


class RetryChildrenRepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings.from_env()
        if not settings.database_url:
            raise unittest.SkipTest("DATABASE_URL required")
        cls.settings = settings
        cls.db = Database(settings)

    def repo(self):
        return OperationRepository(self.db, self.settings)

    def parent(self):
        repo = self.repo()
        parent = repo.create_prepared(
            operation_type="AKAMAI_MFA_DEVICE_RESET",
            domain="akamai_mfa",
            actor_context={"actor": "retry-it"},
            session_context={"session": "retry-it"},
            prepared_interaction_ref="parent-prepare",
            target_identity={"username": "retry-user"},
            destructive_target={
                "device_id": "target",
                "postcheck_factor_baseline": [],
            },
            prepared_snapshot={},
            request_id="prepare-parent",
        )
        return repo.transition(
            parent.operation_id,
            expected_status=OperationStatus.PREPARED,
            new_status=OperationStatus.REQUIRES_RECONFIRMATION,
            actor_context={"actor": "retry-it"},
            session_context={"session": "retry-it"},
            event_type="TEST_REQUIRES_RECONFIRMATION",
            request_id="to-reconfirm",
            outcome_code="test_target_remains",
        )

    def create_child(self, parent_id, interaction):
        return self.repo().create_retry_child(
            parent_operation_id=parent_id,
            operation_type="AKAMAI_MFA_DEVICE_RESET",
            domain="akamai_mfa",
            actor_context={"actor": "retry-it"},
            session_context={"session": "retry-it"},
            prepared_interaction_ref=interaction,
            target_identity={"username": "retry-user"},
            destructive_target={
                "device_id": "target",
                "postcheck_factor_baseline": [],
            },
            prepared_snapshot={"retry_child": True},
            request_id=interaction,
        )

    def test_child_has_independent_prepared_state_and_parent_link(self):
        parent = self.parent()
        child = self.create_child(parent.operation_id, "retry-prepare-1")

        self.assertEqual(child.parent_operation_id, parent.operation_id)
        self.assertEqual(child.status, OperationStatus.PREPARED)
        self.assertEqual(child.execution_attempts, 0)
        self.assertIsNone(child.confirmed_at)
        self.assertGreater(child.expires_at, datetime.now(timezone.utc))

        parent_after = self.repo().get(parent.operation_id)
        self.assertEqual(
            parent_after.status,
            OperationStatus.REQUIRES_RECONFIRMATION,
        )

    def test_child_requires_later_interaction_for_confirmation(self):
        parent = self.parent()
        child = self.create_child(parent.operation_id, "retry-prepare-same")

        with self.assertRaises(Exception) as ctx:
            self.repo().confirm(
                child.operation_id,
                actor_context={"actor": "retry-it"},
                session_context={"session": "retry-it"},
                confirmation_interaction_ref="retry-prepare-same",
                request_id="confirm-same",
            )

        self.assertIn("interação posterior", str(ctx.exception))

    def test_parent_can_create_only_one_direct_child_under_concurrency(self):
        parent = self.parent()
        barrier = threading.Barrier(2)

        def attempt(index):
            barrier.wait()
            try:
                child = self.create_child(
                    parent.operation_id,
                    f"retry-concurrent-{index}",
                )
                return ("ok", child.operation_id)
            except OperationStateConflict as exc:
                return ("conflict", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))

        self.assertEqual(sum(1 for kind, _ in results if kind == "ok"), 1)
        self.assertEqual(
            sum(1 for kind, _ in results if kind == "conflict"),
            1,
        )

    def test_non_reconfirmation_parent_cannot_create_child(self):
        repo = self.repo()
        parent = repo.create_prepared(
            operation_type="AKAMAI_MFA_DEVICE_RESET",
            domain="akamai_mfa",
            actor_context={"actor": "retry-it"},
            session_context={"session": "retry-it"},
            prepared_interaction_ref="parent-prepare",
            target_identity={"username": "retry-user"},
            destructive_target={"device_id": "target"},
            prepared_snapshot={},
        )

        with self.assertRaises(OperationStateConflict):
            self.create_child(parent.operation_id, "retry-invalid-state")


if __name__ == "__main__":
    unittest.main()
