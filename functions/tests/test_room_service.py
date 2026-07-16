import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import room_service  # noqa: E402


class FakeDocument:
    def __init__(self, document_id, data=None):
        self.id = document_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})

    def get(self):
        return self


class FakeQuery:
    def __init__(self, documents, field, value):
        self._documents = documents
        self._field = field
        self._value = value

    def get(self):
        return [doc for doc in self._documents if doc.to_dict().get(self._field) == self._value]


class FakeCollection:
    def __init__(self, documents):
        self._documents = documents

    def document(self, document_id):
        return next(
            (doc for doc in self._documents if doc.id == document_id),
            FakeDocument(document_id),
        )

    def where(self, field, _operator, value):
        return FakeQuery(self._documents, field, value)

    def stream(self):
        return list(self._documents)


class FakeDb:
    def __init__(self, rooms):
        self._rooms = FakeCollection(rooms)

    def collection(self, name):
        if name != "rooms":
            raise AssertionError(f"Unexpected collection: {name}")
        return self._rooms


class RoomServiceTest(unittest.TestCase):
    def setUp(self):
        self.original_db = room_service._db

    def tearDown(self):
        room_service._db = self.original_db

    def configure(self, *rooms):
        room_service.configure_room_service(FakeDb(list(rooms)))

    def test_find_room_returns_canonical_id_for_opaque_document_id(self):
        self.configure(
            FakeDocument(
                "room-7202",
                {"roomID": "7202", "name": "집현관 202호", "buildingDetail": "7강의동"},
            )
        )

        room_id, room_data = room_service.find_room("room-7202")

        self.assertEqual("7202", room_id)
        self.assertEqual("집현관 202호", room_data["name"])
        self.assertEqual("7202", room_service.find_room("7202")[0])

    def test_bare_room_number_is_rejected_when_multiple_buildings_match(self):
        self.configure(
            FakeDocument("room-7202", {"roomID": "7202", "name": "집현관 202호"}),
            FakeDocument("room-5202", {"roomID": "5202", "name": "덕문관 202호"}),
        )

        self.assertEqual((None, None), room_service.find_room("202"))


if __name__ == "__main__":
    unittest.main()
