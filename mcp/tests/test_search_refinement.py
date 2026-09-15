import unittest

from app.tools import map_search_result


class SearchRefinementTests(unittest.TestCase):
    def test_refinement_required_discards_backend_candidates(self):
        result = map_search_result(
            {
                "status": "ambiguous",
                "query": "john",
                "count": 5,
                "total_count": 20,
                "refinement_required": True,
                "candidates": [
                    {
                        "user_ref": "usr_must_not_escape",
                        "username": "user1",
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertTrue(result["refinement_required"])
        self.assertEqual(result["total_count"], 20)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["candidates"], [])
        self.assertNotIn("usr_must_not_escape", repr(result))
        self.assertIn("nome completo", result["message"])
        self.assertIn("username", result["message"])

    def test_total_above_five_forces_refinement_fail_closed(self):
        result = map_search_result(
            {
                "status": "ambiguous",
                "query": "john",
                "count": 5,
                "total_count": 12,
                "refinement_required": False,
                "candidates": [
                    {
                        "user_ref": "usr_drop",
                        "username": "user1",
                    }
                ],
            }
        )

        self.assertTrue(result["refinement_required"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["candidates"], [])

    def test_normal_ambiguous_up_to_five_preserves_candidates(self):
        result = map_search_result(
            {
                "status": "ambiguous",
                "query": "john smith",
                "count": 2,
                "total_count": 2,
                "refinement_required": False,
                "candidates": [
                    {
                        "user_ref": "usr_one",
                        "username": "user1",
                    },
                    {
                        "user_ref": "usr_two",
                        "username": "user2",
                    },
                ],
            }
        )

        self.assertFalse(result["refinement_required"])
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["candidates"]), 2)

    def test_contradictory_found_plus_refinement_fails_closed(self):
        result = map_search_result(
            {
                "status": "found",
                "query": "a0000001",
                "count": 1,
                "total_count": 1,
                "refinement_required": True,
                "candidates": [
                    {
                        "user_ref": "usr_one",
                        "username": "a0000001",
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result["code"],
            "unexpected_api_contract",
        )


if __name__ == "__main__":
    unittest.main()
