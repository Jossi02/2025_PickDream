import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import reservation_service  # noqa: E402
from reservation_utils import KST  # noqa: E402


class FakeSnapshot:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocumentRef:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.id = doc_id

    def get(self):
        return FakeSnapshot(self.id, self.collection.documents.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.collection.documents:
            self.collection.documents[self.id].update(dict(data))
        else:
            self.collection.documents[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.collection.documents:
            self.collection.documents[self.id] = {}
        self.collection.documents[self.id].update(dict(data))

    def delete(self):
        self.collection.documents.pop(self.id, None)


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.added = []

    def document(self, doc_id):
        return FakeDocumentRef(self, doc_id)

    def add(self, data):
        doc_id = f"generated-{len(self.added) + 1}"
        self.documents[doc_id] = dict(data)
        self.added.append((doc_id, dict(data)))
        return None, FakeDocumentRef(self, doc_id)


class FakeDb:
    def __init__(self):
        self.collections = {
            "PendingReservations": FakeCollection(),
            "Reservations": FakeCollection(),
        }

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class ReservationFlowTest(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "db": main.db,
            "service_db": reservation_service.db,
            "service__db": reservation_service._db,
            "service_find_room": reservation_service.find_room,
            "service_display_room_label": reservation_service.display_room_label,
            "service_find_conflicting_reservation": reservation_service.find_conflicting_reservation,
            "service_has_conflict": reservation_service.has_conflict,
            "service_find_available_rooms": reservation_service.find_available_rooms,
            "service_find_user_reservation": reservation_service.find_user_reservation,
            "service_list_user_upcoming_reservations": reservation_service.list_user_upcoming_reservations,
        }
        self.db = FakeDb()
        main.db = self.db
        reservation_service.configure_reservation_service(
            self.db,
            room_label_formatter=lambda room_id, room_data=None: f"{room_id} \uac15\uc758\uc2e4",
        )
        reservation_service.find_room = self.fake_find_room
        reservation_service.display_room_label = lambda room_id, room_data=None: f"{room_id} \uac15\uc758\uc2e4"
        reservation_service.find_conflicting_reservation = lambda *args, **kwargs: (None, None)
        reservation_service.has_conflict = lambda *args, **kwargs: False
        reservation_service.find_available_rooms = lambda *args, **kwargs: []

    def tearDown(self):
        main.db = self.originals["db"]
        reservation_service.db = self.originals["service_db"]
        reservation_service._db = self.originals["service__db"]
        reservation_service.find_room = self.originals["service_find_room"]
        reservation_service.display_room_label = self.originals["service_display_room_label"]
        reservation_service.find_conflicting_reservation = self.originals["service_find_conflicting_reservation"]
        reservation_service.has_conflict = self.originals["service_has_conflict"]
        reservation_service.find_available_rooms = self.originals["service_find_available_rooms"]
        reservation_service.find_user_reservation = self.originals["service_find_user_reservation"]
        reservation_service.list_user_upcoming_reservations = self.originals["service_list_user_upcoming_reservations"]

    @staticmethod
    def fake_find_room(room_identifier):
        if not room_identifier:
            return None, None
        room_id = str(room_identifier).strip()
        return room_id, {"roomID": room_id, "name": f"{room_id} \uac15\uc758\uc2e4"}

    @staticmethod
    def response_text(response):
        return response.data.decode("utf-8")

    def test_handle_reserve_missing_details_stores_pending_without_reservation(self):
        response = main.handle_reserve(
            {
                "room": "7202",
                "ownerUid": "uid-123",
            },
            "20201234",
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("\uc2dc\uc791 \uc2dc\uac04", self.response_text(response))
        self.assertIn("\uc774\uc6a9 \uc778\uc6d0 \uc218", self.response_text(response))
        self.assertIn("20201234", self.db.collection("PendingReservations").documents)
        self.assertEqual({}, self.db.collection("Reservations").documents)

    def test_handle_reserve_needs_confirmation_creates_pending_and_card(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)

        response = main.handle_reserve(
            {
                "room": "7202",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "5\uba85",
                "ownerUid": "uid-123",
                "needsConfirmation": True,
                "_structuredResponse": True,
            },
            "20201234",
        )

        self.assertEqual(200, response.status_code)
        payload = json.loads(self.response_text(response))
        self.assertEqual("\uc608\uc57d \ub0b4\uc6a9\uc744 \ud655\uc778\ud574 \uc8fc\uc138\uc694", payload["title"])
        self.assertEqual("confirmation", payload["cards"][0]["type"])
        self.assertEqual("\uc608\uc57d \ud655\uc815", payload["cards"][0]["actions"][0]["label"])
        pending = self.db.collection("PendingReservations").documents["20201234"]
        self.assertEqual("7202", pending["room"])
        self.assertEqual("5\uba85", pending["eventParticipants"])
        self.assertEqual({}, self.db.collection("Reservations").documents)

    def test_handle_confirm_reservation_persists_manual_compatible_document(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        self.db.collection("PendingReservations").document("20201234").set(
            {
                "room": "7202",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "5",
                "ownerUid": "uid-123",
                "flowType": main.FLOW_NEW_RESERVATION,
            }
        )

        response = main.handle_confirm_reservation({"ownerUid": "uid-123"}, "20201234")

        self.assertEqual(200, response.status_code)
        self.assertNotIn("20201234", self.db.collection("PendingReservations").documents)
        self.assertEqual(1, len(self.db.collection("Reservations").added))
        _, reservation = self.db.collection("Reservations").added[0]
        self.assertEqual("7202", reservation["roomID"])
        self.assertEqual(5, reservation["eventParticipants"])
        self.assertEqual("20201234", reservation["userID"])
        self.assertEqual("uid-123", reservation["ownerUid"])
        self.assertNotIn("startTimestamp", reservation)
        self.assertNotIn("endTimestamp", reservation)

    def test_new_confirmation_discards_stale_replacement_target(self):
        start = datetime(2099, 7, 12, 13, 0, tzinfo=KST)
        self.db.collection("PendingReservations").document("20201234").set(
            {
                "room": "7202",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "5",
                "ownerUid": "uid-123",
                "flowType": main.FLOW_CHANGE_EXISTING_RESERVATION,
                "replaceReservationId": "deleted-reservation",
            }
        )

        proposal = main.handle_reserve(
            {
                "room": "4303",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "3",
                "ownerUid": "uid-123",
                "needsConfirmation": True,
            },
            "20201234",
        )

        self.assertEqual(200, proposal.status_code)
        pending = self.db.collection("PendingReservations").documents["20201234"]
        self.assertEqual(main.FLOW_NEW_RESERVATION, pending["flowType"])
        self.assertNotIn("replaceReservationId", pending)

        confirmation = main.handle_confirm_reservation(
            {"ownerUid": "uid-123"},
            "20201234",
        )

        self.assertEqual(200, confirmation.status_code)
        self.assertIn("예약되었습니다", self.response_text(confirmation))
        self.assertEqual(1, len(self.db.collection("Reservations").added))

    def test_deleted_change_target_returns_conflict_instead_of_server_error(self):
        start = datetime(2099, 7, 12, 13, 0, tzinfo=KST)
        self.db.collection("PendingReservations").document("20201234").set(
            {
                "room": "4303",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "3",
                "ownerUid": "uid-123",
                "flowType": main.FLOW_CHANGE_EXISTING_RESERVATION,
                "replaceReservationId": "deleted-reservation",
            }
        )

        response = main.handle_confirm_reservation(
            {"ownerUid": "uid-123"},
            "20201234",
        )

        self.assertEqual(409, response.status_code)
        self.assertIn("변경할 기존 예약을 찾을 수 없어요", self.response_text(response))
        self.assertNotIn(
            "20201234",
            self.db.collection("PendingReservations").documents,
        )

    def test_handle_reserve_room_conflict_returns_alternative_card(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        reservation_service.has_conflict = lambda field, *args, **kwargs: field == "roomID"
        reservation_service.find_available_rooms = lambda *args, **kwargs: [
            (30, "4303", "room-doc-4303", {"roomID": "4303", "name": "4303 \uac15\uc758\uc2e4"})
        ]

        response = main.handle_reserve(
            {
                "room": "7202",
                "startTime": start.isoformat(),
                "duration": 2,
                "eventParticipants": "5",
                "ownerUid": "uid-123",
                "_structuredResponse": True,
            },
            "20201234",
        )

        self.assertEqual(200, response.status_code)
        payload = json.loads(self.response_text(response))
        self.assertEqual("\ub300\uccb4 \uac15\uc758\uc2e4 \uc81c\uc548", payload["title"])
        self.assertEqual("alternative", payload["cards"][0]["type"])
        self.assertEqual("4303 \uac15\uc758\uc2e4", payload["cards"][0]["roomName"])
        pending = self.db.collection("PendingReservations").documents["20201234"]
        self.assertEqual("4303", pending["room"])

    def test_handle_cancel_reservation_without_target_lists_candidates(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        end = start + timedelta(hours=2)
        reservation_service.list_user_upcoming_reservations = lambda user_id, limit=5: [
            (
                start,
                "7202 \uac15\uc758\uc2e4",
                {
                    "startTime": main.format_korean_time(start),
                    "endTime": main.format_korean_time(end),
                    "eventParticipants": 5,
                },
            ),
            (
                start + timedelta(days=1),
                "4303 \uac15\uc758\uc2e4",
                {
                    "startTime": main.format_korean_time(start + timedelta(days=1)),
                    "endTime": main.format_korean_time(end + timedelta(days=1)),
                    "eventParticipants": 4,
                },
            ),
        ]

        response = main.handle_cancel_reservation({}, "20201234")
        text = self.response_text(response)

        self.assertEqual(200, response.status_code)
        self.assertIn("7202 \uac15\uc758\uc2e4", text)
        self.assertIn("4303 \uac15\uc758\uc2e4", text)
        self.assertIn("5\uba85", text)
        self.assertIn("4\uba85", text)

    def test_handle_change_reservation_updates_existing_document(self):
        original_start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        original_end = original_start + timedelta(hours=2)
        new_start = datetime(2099, 7, 12, 12, 0, tzinfo=KST)
        self.db.collection("Reservations").document("res-1").set(
            {"roomID": "7202", "userID": "20201234"}
        )
        reservation_service.find_user_reservation = lambda *args, **kwargs: (
            "res-1",
            {"roomID": "7202", "userID": "20201234"},
            original_start,
            original_end,
        )
        reservation_service.has_conflict = lambda *args, **kwargs: False

        response = main.handle_change_reservation(
            {
                "newRoom": "4303",
                "startTime": new_start.isoformat(),
                "duration": 2,
                "eventParticipants": "4\uba85",
            },
            "20201234",
        )

        self.assertEqual(200, response.status_code)
        updated = self.db.collection("Reservations").documents["res-1"]
        self.assertEqual("4303", updated["roomID"])
        self.assertEqual(main.format_korean_time(new_start), updated["startTime"])
        self.assertEqual(main.format_korean_time(new_start + timedelta(hours=2)), updated["endTime"])
        self.assertEqual(4, updated["eventParticipants"])

    def test_handle_change_selection_returns_structured_reservation_cards(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        end = start + timedelta(hours=2)
        reservation_service.list_user_upcoming_reservations = lambda user_id, limit=5: [
            (
                start,
                "7202 \uac15\uc758\uc2e4",
                {
                    "_documentId": "res-1",
                    "roomID": "7202",
                    "startTime": main.format_korean_time(start),
                    "endTime": main.format_korean_time(end),
                    "eventParticipants": 5,
                },
            )
        ]

        response = reservation_service.handle_change_reservation_selection(
            {
                "ownerUid": "uid-123",
                "_structuredResponse": True,
            },
            "20201234",
        )

        self.assertEqual(200, response.status_code)
        payload = json.loads(self.response_text(response))
        self.assertEqual("\ubcc0\uacbd\ud560 \uc608\uc57d\uc744 \uc120\ud0dd\ud574 \uc8fc\uc138\uc694", payload["title"])
        self.assertEqual("change_selection", payload["cards"][0]["type"])
        self.assertEqual("\uc608\uc57d \ubcc0\uacbd \ub300\uc0c1 \uc120\ud0dd::res-1", payload["cards"][0]["actions"][0]["message"])
        pending = self.db.collection("PendingReservations").documents["20201234"]
        self.assertTrue(pending["awaitingReservationSelection"])

    def test_select_change_target_stores_exact_reservation_for_followup(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        end = start + timedelta(hours=2)
        self.db.collection("Reservations").document("res-1").set(
            {
                "roomID": "7202",
                "userID": "20201234",
                "ownerUid": "uid-123",
                "startTime": main.format_korean_time(start),
                "endTime": main.format_korean_time(end),
                "eventParticipants": 5,
            }
        )
        self.db.collection("PendingReservations").document("20201234").set(
            {
                "flowType": main.FLOW_CHANGE_EXISTING_RESERVATION,
                "awaitingReservationSelection": True,
                "ownerUid": "uid-123",
            }
        )

        response = reservation_service.handle_select_reservation_for_change(
            "res-1",
            "20201234",
            structured=True,
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("3\uba85\uc73c\ub85c \ubcc0\uacbd\ud574\uc918", self.response_text(response))
        pending = self.db.collection("PendingReservations").documents["20201234"]
        self.assertEqual("res-1", pending["replaceReservationId"])
        self.assertTrue(pending["awaitingChangeDetails"])

    def test_select_change_target_applies_requested_participant_count_to_exact_reservation(self):
        start = datetime(2099, 7, 11, 11, 0, tzinfo=KST)
        end = start + timedelta(hours=2)
        self.db.collection("Reservations").document("res-1").set(
            {
                "roomID": "7202",
                "userID": "20201234",
                "ownerUid": "uid-123",
                "startTime": main.format_korean_time(start),
                "endTime": main.format_korean_time(end),
                "eventParticipants": 5,
            }
        )
        self.db.collection("PendingReservations").document("20201234").set(
            {
                "flowType": main.FLOW_CHANGE_EXISTING_RESERVATION,
                "awaitingReservationSelection": True,
                "ownerUid": "uid-123",
                "requestedEventParticipants": "3",
            }
        )

        response = reservation_service.handle_select_reservation_for_change(
            "res-1",
            "20201234",
            structured=True,
        )

        self.assertEqual(200, response.status_code)
        updated = self.db.collection("Reservations").documents["res-1"]
        self.assertEqual(3, updated["eventParticipants"])
        self.assertEqual("7202", updated["roomID"])


if __name__ == "__main__":
    unittest.main()
