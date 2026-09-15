import unittest

from app.api.v2.schemas import EaaUserSearchResponse
from app.clients.eaa import EaaClient


class EaaSearchPageTests(unittest.TestCase):
    def test_meta_total_count_is_preserved(self):
        payload = {
            "objects": [
                {"username": f"user{i}"}
                for i in range(5)
            ],
            "meta": {
                "total_count": 20,
            },
        }

        page = EaaClient.parse_search_page(payload)

        self.assertEqual(len(page.users), 5)
        self.assertEqual(page.total_count, 20)
        self.assertTrue(page.has_more)

    def test_meta_next_marks_more_results(self):
        payload = {
            "objects": [
                {"username": f"user{i}"}
                for i in range(5)
            ],
            "meta": {
                "next": "opaque-next-page",
            },
        }

        page = EaaClient.parse_search_page(payload)

        self.assertEqual(len(page.users), 5)
        self.assertIsNone(page.total_count)
        self.assertTrue(page.has_more)

    def test_no_metadata_keeps_observed_page_only(self):
        payload = {
            "objects": [
                {"username": "user1"},
                {"username": "user2"},
            ],
        }

        page = EaaClient.parse_search_page(payload)

        self.assertEqual(len(page.users), 2)
        self.assertIsNone(page.total_count)
        self.assertFalse(page.has_more)

    def test_response_schema_exposes_refinement_contract(self):
        response = EaaUserSearchResponse(
            status="ambiguous",
            query="john",
            count=0,
            total_count=20,
            refinement_required=True,
            candidates=[],
        )

        self.assertEqual(response.total_count, 20)
        self.assertTrue(response.refinement_required)
        self.assertEqual(response.candidates, [])


if __name__ == "__main__":
    unittest.main()
