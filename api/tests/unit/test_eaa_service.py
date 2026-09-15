import unittest

from app.domain.eaa import EaaUserRecord
from app.services.eaa import EaaSearchResultType, EaaService


def rec(username=None, sam=None, display="User", reset="internal"):
    return EaaUserRecord(
        username=username,
        samaccountname=sam,
        display_name=display,
        status="ACTIVE",
        login_mfa=True,
        internal_reset_id=reset,
        raw={},
    )


class EaaResolutionTests(unittest.TestCase):
    def test_exact_username_case_insensitive_resolves(self):
        result = EaaService.resolve("A0000001", [rec(username="a0000001")])
        self.assertEqual(result.result, EaaSearchResultType.FOUND)
        self.assertEqual(result.users[0].username, "a0000001")
        self.assertEqual(result.resolved_internal.internal_reset_id, "internal")

    def test_exact_samaccountname_resolves(self):
        result = EaaService.resolve("A0000001", [rec(username="alias", sam="a0000001")])
        self.assertEqual(result.result, EaaSearchResultType.FOUND)
        self.assertEqual(result.resolved_internal.samaccountname, "a0000001")

    def test_empty_is_not_found(self):
        result = EaaService.resolve("u", [])
        self.assertEqual(result.result, EaaSearchResultType.NOT_FOUND)
        self.assertEqual(result.users, ())

    def test_name_or_non_exact_results_are_ambiguous_candidates(self):
        result = EaaService.resolve(
            "john",
            [rec(username="jdoe1"), rec(username="jdoe2")],
        )
        self.assertEqual(result.result, EaaSearchResultType.AMBIGUOUS)
        self.assertEqual(len(result.candidates), 2)

    def test_exactly_five_non_exact_candidates_are_allowed(self):
        result = EaaService.resolve(
            "john",
            [rec(username=f"user{i}") for i in range(5)],
        )
        self.assertEqual(result.result, EaaSearchResultType.AMBIGUOUS)
        self.assertFalse(result.refinement_required)
        self.assertIsNone(result.total_count)
        self.assertEqual(len(result.candidates), 5)

    def test_more_than_five_requires_refinement_and_emits_no_candidates(self):
        result = EaaService.resolve(
            "john",
            [rec(username=f"user{i}") for i in range(6)],
        )
        self.assertEqual(result.result, EaaSearchResultType.AMBIGUOUS)
        self.assertTrue(result.refinement_required)
        self.assertIsNone(result.total_count)
        self.assertEqual(result.candidates, ())

    def test_has_more_without_total_requires_refinement_without_inventing_total(self):
        result = EaaService.resolve(
            "john",
            [rec(username=f"user{i}") for i in range(5)],
            has_more=True,
        )
        self.assertEqual(result.result, EaaSearchResultType.AMBIGUOUS)
        self.assertTrue(result.refinement_required)
        self.assertIsNone(result.total_count)
        self.assertEqual(result.candidates, ())

    def test_upstream_total_above_five_requires_refinement_even_with_five_objects(self):
        result = EaaService.resolve(
            "john",
            [rec(username=f"user{i}") for i in range(5)],
            total_count=20,
            has_more=True,
        )
        self.assertEqual(result.result, EaaSearchResultType.AMBIGUOUS)
        self.assertTrue(result.refinement_required)
        self.assertEqual(result.total_count, 20)
        self.assertEqual(result.candidates, ())

    def test_exact_username_wins_even_when_upstream_result_is_broad(self):
        result = EaaService.resolve(
            "A0000001",
            [
                rec(username="a0000001"),
                rec(username="other1"),
                rec(username="other2"),
                rec(username="other3"),
                rec(username="other4"),
            ],
            total_count=20,
            has_more=True,
        )
        self.assertEqual(result.result, EaaSearchResultType.FOUND)
        self.assertFalse(result.refinement_required)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.users[0].username, "a0000001")


if __name__ == "__main__":
    unittest.main()
