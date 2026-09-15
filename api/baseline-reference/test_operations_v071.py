import os
import tempfile
import unittest

from app.operations import (
    OperationConflict,
    OperationExpired,
    OperationForbidden,
    OperationStore,
)


class OperationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "ops.db")
        self.store = OperationStore(self.db, ttl_seconds=300, retention_seconds=3600)

    def tearDown(self):
        self.tmp.cleanup()

    def _prepare(self, subject="sub-1", username="80000001"):
        return self.store.prepare(
            username=username,
            display_name="Test User",
            reset_user_id="uuid-reset",
            amfa_user_id="user_amfa",
            device_count_before=1,
            cleanup_required=True,
            requested_by_sub=subject,
            requested_by="operator@example",
        )

    def test_prepare_reuses_same_subject_prepared_operation(self):
        first, reused1 = self._prepare()
        second, reused2 = self._prepare()
        self.assertFalse(reused1)
        self.assertTrue(reused2)
        self.assertEqual(first.operation_id, second.operation_id)

    def test_prepare_blocks_concurrent_operation_for_same_user(self):
        self._prepare(subject="sub-1")
        with self.assertRaises(OperationConflict):
            self._prepare(subject="sub-2")

    def test_claim_is_bound_to_requester(self):
        op, _ = self._prepare(subject="sub-1")
        with self.assertRaises(OperationForbidden):
            self.store.claim(op.operation_id, "sub-2")

    def test_completed_operation_is_idempotent(self):
        op, _ = self._prepare()
        claim = self.store.claim(op.operation_id, "sub-1")
        self.assertFalse(claim.replayed)
        result = {
            "status": "success",
            "operation_id": op.operation_id,
            "username": op.username,
            "otp_reset": "success",
            "device_cleanup": "removed",
            "device_count_before": 1,
            "device_cleanup_verified": True,
            "replayed": False,
            "request_id": "req-1",
        }
        self.store.complete(op.operation_id, result)
        replay = self.store.claim(op.operation_id, "sub-1")
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.record.result["request_id"], "req-1")

    def test_expired_operation_cannot_be_claimed(self):
        fast = OperationStore(self.db, ttl_seconds=-1, retention_seconds=3600)
        op, _ = fast.prepare(
            username="u2",
            display_name=None,
            reset_user_id="uuid",
            amfa_user_id=None,
            device_count_before=None,
            cleanup_required=False,
            requested_by_sub="sub-1",
            requested_by="op",
        )
        with self.assertRaises(OperationExpired):
            fast.claim(op.operation_id, "sub-1")


if __name__ == "__main__":
    unittest.main()
