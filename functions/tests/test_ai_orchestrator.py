import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firebase_functions import https_fn  # noqa: E402

from ai_orchestrator import process_ai_message  # noqa: E402


class FakeSnapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocumentRef:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.id = doc_id

    def get(self):
        return FakeSnapshot(self.collection.documents.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.collection.documents:
            self.collection.documents[self.id].update(dict(data))
        else:
            self.collection.documents[self.id] = dict(data)

    def delete(self):
        self.collection.documents.pop(self.id, None)


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def document(self, doc_id):
        return FakeDocumentRef(self, doc_id)


class FakeDb:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class AiOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.handlers = {}

    def route(self, message):
        return process_ai_message(
            db=self.db,
            genai_client=None,
            handlers=self.handlers,
            faq_rules="rules",
            user_input=message,
            user_id="20201234",
            uid="uid-123",
            supports_structured_response=True,
        )

    @staticmethod
    def response_text(response):
        return response.data.decode("utf-8")

    def test_new_reservation_reset_is_handled_without_gemini(self):
        self.db.collection("PendingReservations").documents["20201234"] = {
            "room": "7202"
        }

        response = self.route("새 예약 만들고 싶어")

        self.assertEqual(200, response.status_code)
        self.assertIn("새 예약으로 시작할게요", self.response_text(response))
        self.assertNotIn(
            "20201234",
            self.db.collection("PendingReservations").documents,
        )
        history = self.db.collection("ChatHistory").documents["20201234"]
        self.assertEqual("새 예약 만들고 싶어", history["messages"][-2]["text"])

    def test_my_reservations_uses_injected_handler_without_gemini(self):
        calls = []

        def handle_my_reservations(query, user_id):
            calls.append((query, user_id))
            return https_fn.Response("현재 예약 1건", status=200)

        self.handlers["my_reservations"] = handle_my_reservations

        response = self.route("내 예약 보여줘")

        self.assertEqual(200, response.status_code)
        self.assertEqual("현재 예약 1건", self.response_text(response))
        self.assertEqual(
            [({"ownerUid": "uid-123"}, "20201234")],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
