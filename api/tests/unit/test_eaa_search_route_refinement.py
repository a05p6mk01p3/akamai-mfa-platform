import unittest

from app.api.v2.eaa import search_eaa_users
from app.services.eaa import EaaSearchResult, EaaSearchResultType


class _Service:
    def search(self, query):
        return EaaSearchResult(
            result=EaaSearchResultType.AMBIGUOUS,
            candidates=(),
            total_count=20,
            refinement_required=True,
        )


class _Refs:
    def issue_user_ref(self, *args, **kwargs):
        raise AssertionError(
            "user_ref must not be issued for a broad search"
        )


class _Context:
    actor_context = "actor"
    session_context = "session"


class BroadSearchRouteTests(unittest.TestCase):
    def test_broad_search_emits_no_safe_reference(self):
        response = search_eaa_users(
            request=None,
            q="john",
            context=_Context(),
            service=_Service(),
            refs=_Refs(),
        )

        self.assertEqual(response.status, "ambiguous")
        self.assertTrue(response.refinement_required)
        self.assertEqual(response.total_count, 20)
        self.assertEqual(response.count, 0)
        self.assertEqual(response.candidates, [])


if __name__ == "__main__":
    unittest.main()
