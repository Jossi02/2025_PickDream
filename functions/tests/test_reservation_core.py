import os
import sys
import unittest
from datetime import datetime
from pathlib import Path


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import reservation_service  # noqa: E402
from reservation_utils import KST  # noqa: E402


class FakeReservationDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class ReservationCoreTest(unittest.TestCase):
    def test_build_reservation_document_uses_manual_reservation_schema(self):
        start = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 13, 0, tzinfo=KST)
        query = {
            "room": "7202",
            "eventName": "\uc2a4\ud130\ub514",
            "eventDescription": "\ud504\ub85c\uc81d\ud2b8 \ud68c\uc758",
            "eventTarget": "\ud300\uc6d0",
            "eventParticipants": "5\uba85",
            "status": "\ub300\uae30",
        }

        document = main.build_reservation_document(query, "20201234", "uid-123", start, end)

        self.assertEqual("", document["documentId"])
        self.assertEqual("7202", document["roomID"])
        self.assertEqual(main.format_korean_time(start), document["startTime"])
        self.assertEqual(main.format_korean_time(end), document["endTime"])
        self.assertEqual("\uc2a4\ud130\ub514", document["eventName"])
        self.assertEqual("\ud504\ub85c\uc81d\ud2b8 \ud68c\uc758", document["eventDescription"])
        self.assertEqual("\ud300\uc6d0", document["eventTarget"])
        self.assertEqual(5, document["eventParticipants"])
        self.assertEqual("\ub300\uae30", document["status"])
        self.assertEqual("20201234", document["userID"])
        self.assertEqual("uid-123", document["ownerUid"])
        self.assertNotIn("startTimestamp", document)
        self.assertNotIn("endTimestamp", document)

    def test_build_reservation_document_defaults_match_ai_reservation_policy(self):
        start = datetime(2026, 7, 10, 9, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        query = {"room": "5101", "eventParticipants": None}

        document = main.build_reservation_document(query, "20201234", None, start, end)

        self.assertEqual("\ucd94\ucc9c \uc608\uc57d", document["eventName"])
        self.assertEqual("", document["eventDescription"])
        self.assertEqual("", document["eventTarget"])
        self.assertEqual(1, document["eventParticipants"])
        self.assertEqual("\ub300\uae30", document["status"])
        self.assertEqual("", document["ownerUid"])

    def test_parse_reservation_start_and_duration_assigns_kst_to_naive_start(self):
        query = {"startTime": "2026-07-10T11:00:00", "duration": "2"}

        start, duration = main.parse_reservation_start_and_duration(query)

        self.assertEqual(datetime(2026, 7, 10, 11, 0, tzinfo=KST), start)
        self.assertEqual(2, duration)

    def test_reservation_time_range_prefers_timestamp_fields(self):
        start = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 13, 0, tzinfo=KST)
        data = {
            "startTimestamp": start,
            "endTimestamp": end,
            "startTime": "",
            "endTime": "",
        }

        self.assertEqual((start, end), main.reservation_time_range(data))

    def test_reservation_time_range_falls_back_to_korean_strings(self):
        start = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 13, 0, tzinfo=KST)
        data = {
            "startTime": main.format_korean_time(start),
            "endTime": main.format_korean_time(end),
        }

        self.assertEqual((start, end), main.reservation_time_range(data))

    def test_normalize_event_participants_recovers_from_keywords(self):
        query = {"keywords": ["\ub9c8\uc774\ud06c", "5\uba85"]}

        self.assertEqual("5", main.normalize_event_participants(query))

    def test_parse_participants_int_defaults_to_one_when_blank(self):
        self.assertEqual(5, main.parse_participants_int("5\uba85"))
        self.assertEqual(1, main.parse_participants_int(""))
        self.assertEqual(1, main.parse_participants_int(None))

    def test_has_conflict_ignores_cancelled_reservations_and_detects_overlap(self):
        start = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 13, 0, tzinfo=KST)
        documents = [
            FakeReservationDoc(
                "cancelled",
                {
                    "status": "\ucde8\uc18c",
                    "startTime": main.format_korean_time(start),
                    "endTime": main.format_korean_time(end),
                },
            ),
            FakeReservationDoc(
                "active",
                {
                    "status": "\ub300\uae30",
                    "startTime": main.format_korean_time(start),
                    "endTime": main.format_korean_time(end),
                },
            ),
        ]
        original_loader = reservation_service._reservation_documents_for_field
        reservation_service._reservation_documents_for_field = lambda field, value: documents
        try:
            self.assertTrue(main.has_conflict("roomID", "7202", start, end))
            self.assertFalse(main.has_conflict("roomID", "7202", start, end, exclude_id="active"))
        finally:
            reservation_service._reservation_documents_for_field = original_loader

    def test_find_conflicting_reservation_returns_matching_document(self):
        start = datetime(2026, 7, 10, 11, 0, tzinfo=KST)
        end = datetime(2026, 7, 10, 13, 0, tzinfo=KST)
        expected_data = {
            "status": "\ub300\uae30",
            "roomID": "7202",
            "startTime": main.format_korean_time(start),
            "endTime": main.format_korean_time(end),
        }
        original_loader = reservation_service._reservation_documents_for_field
        reservation_service._reservation_documents_for_field = lambda field, value: [
            FakeReservationDoc("reservation-1", expected_data)
        ]
        try:
            doc_id, data = main.find_conflicting_reservation("roomID", "7202", start, end)
        finally:
            reservation_service._reservation_documents_for_field = original_loader

        self.assertEqual("reservation-1", doc_id)
        self.assertEqual(expected_data, data)


if __name__ == "__main__":
    unittest.main()
