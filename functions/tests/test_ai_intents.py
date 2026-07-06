import os
import sys
import unittest
import json
from pathlib import Path
from datetime import datetime


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from reservation_utils import KST  # noqa: E402


class AiIntentTest(unittest.TestCase):
    def test_cancel_reservation_patterns(self):
        self.assertTrue(main.is_cancel_reservation_request("\uc608\uc57d \ucde8\uc18c\ud574\uc918"))
        self.assertTrue(main.is_cancel_reservation_request("\uc608\uc57d\uc744 \ucde8\uc18c\ud558\uace0 \uc2f6\uc5b4"))
        self.assertTrue(main.is_cancel_reservation_request("7202 \uac15\uc758\uc2e4 \ucde8\uc18c\ud560\uac8c"))
        self.assertFalse(main.is_cancel_reservation_request("\uc608\uc57d\ud655\uc815"))

    def test_change_reservation_patterns(self):
        self.assertTrue(main.is_change_reservation_request("12\uc2dc\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertTrue(main.is_change_reservation_request("5101 \uac15\uc758\uc2e4\ub85c \ubc14\uafd4\uc918"))
        self.assertTrue(main.is_change_reservation_request("\uc778\uc6d0 6\uba85\uc73c\ub85c \ubc14\uafd4\uc918"))
        self.assertFalse(main.is_change_reservation_request("\uc608\uc57d \ucde8\uc18c\ud574\uc918"))

    def test_explicit_change_reservation_patterns(self):
        self.assertTrue(main.is_explicit_change_reservation_request("\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertTrue(main.is_explicit_change_reservation_request("5101 \uac15\uc758\uc2e4\ub85c \ubc14\uafd4\uc918"))
        self.assertFalse(main.is_explicit_change_reservation_request("\ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ud574\uc918"))

    def test_my_reservations_patterns(self):
        self.assertTrue(main.is_my_reservations_request("\ub0b4 \uc608\uc57d \ubcf4\uc5ec\uc918"))
        self.assertTrue(main.is_my_reservations_request("\uc608\uc57d \ub0b4\uc5ed \uc870\ud68c"))
        self.assertFalse(main.is_my_reservations_request("\uc608\uc57d\ud655\uc815"))
        self.assertFalse(main.is_my_reservations_request("\ub0b4 \uc608\uc57d 12\uc2dc\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertFalse(main.is_my_reservations_request("\ub0b4 \uc608\uc57d \ucde8\uc18c\ud574\uc918"))

    def test_reservation_request_is_not_confirmation(self):
        text = "\ubaa8\ub808 \uc624\uc804 11\uc2dc\uc5d0 7202 \uac15\uc758\uc2e4 \uc608\uc57d\ud574\uc918. 5\uba85\uc774\uc57c"

        self.assertTrue(main.is_reservation_request_text(text))
        self.assertFalse(main.is_reservation_confirmation(text))
        self.assertTrue(main.is_reservation_confirmation("\uc608\uc57d \ud655\uc815"))

    def test_recommendation_queries_are_not_reservation_requests(self):
        self.assertFalse(main.is_reservation_request_text("6명이서 이용하기 좋은 강의실은 어디야?"))
        self.assertFalse(main.is_reservation_request_text("지금 예약 가능한 강의실 알려줘"))
        self.assertFalse(main.is_reservation_request_text("마이크 있는 강의실 추천해줘"))
        self.assertTrue(main.is_reservation_request_text("모레 오전 11시에 7202 강의실 예약해줘. 5명이야"))

    def test_extract_recommendation_keywords(self):
        self.assertEqual(["6명"], main.extract_recommendation_keywords("6명이서 이용하기 좋은 강의실은 어디야?"))
        self.assertIn("지금", main.extract_recommendation_keywords("지금 예약 가능한 강의실 알려줘"))
        self.assertIn("마이크", main.extract_recommendation_keywords("마이크 있는 강의실 추천해줘"))

    def test_make_ai_response_is_backward_compatible(self):
        text_response = main.make_ai_response("plain text")
        self.assertEqual("plain text", text_response.data.decode("utf-8"))

        json_response = main.make_ai_response(
            "structured text",
            query={"_structuredResponse": True},
            title="title",
            cards=[main.ai_card("confirmation", "7202 강의실")],
        )
        payload = json.loads(json_response.data.decode("utf-8"))
        self.assertEqual("structured text", payload["text"])
        self.assertEqual("title", payload["title"])
        self.assertEqual("7202 강의실", payload["cards"][0]["roomName"])

    def test_room_and_duration_parsing(self):
        self.assertEqual(["7202", "5101"], main.extract_room_ids("7202\ub97c 5101\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertEqual(2, main.parse_duration_hours("2\uc2dc\uac04\uc73c\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertEqual(6, main.parse_participant_count("6\uba85\uc73c\ub85c \ubc14\uafd4\uc918"))

    def test_direct_reservation_sentence_parses_all_required_fields(self):
        text = "\ubaa8\ub808 \uc624\uc804 11\uc2dc\uc5d0 7202 \uac15\uc758\uc2e4 \uc608\uc57d\ud574\uc918. 5\uba85\uc774\uc57c"
        now = datetime(2026, 7, 5, 21, 0, tzinfo=KST)
        start = main.parse_natural_korean_datetime(text, now)

        self.assertEqual("7202", main.extract_room_id(text))
        self.assertEqual(5, main.parse_participant_count(text))
        self.assertEqual(datetime(2026, 7, 7, 11, 0, tzinfo=KST), start)

    def test_enrich_query_from_direct_parse_fills_missing_reserve_args(self):
        query = {"ownerUid": "uid", "needsConfirmation": True}
        start = datetime(2026, 7, 7, 11, 0, tzinfo=KST)

        main.enrich_query_from_direct_parse(
            query,
            room_id="7202",
            start=start,
            participants=5,
            duration=None,
        )

        self.assertEqual("7202", query["room"])
        self.assertEqual(start.isoformat(), query["startTime"])
        self.assertEqual("5", query["eventParticipants"])

    def test_recover_reserve_fields_from_raw_text_fills_missing_handle_reserve_args(self):
        query = {"room": "7202"}
        text = "\ubaa8\ub808 \uc624\uc804 11\uc2dc\uc5d0 7202 \uac15\uc758\uc2e4 \uc608\uc57d\ud574\uc918. 5\uba85\uc774\uc57c"
        now = datetime(2026, 7, 5, 21, 0, tzinfo=KST)

        main.recover_reserve_fields_from_text(query, text, now)

        self.assertEqual("7202", query["room"])
        self.assertEqual(datetime(2026, 7, 7, 11, 0, tzinfo=KST).isoformat(), query["startTime"])
        self.assertEqual("5", query["eventParticipants"])

    def test_pending_flow_type_inference(self):
        self.assertEqual(
            main.FLOW_NEW_RESERVATION,
            main.infer_pending_flow_type({}),
        )
        self.assertEqual(
            main.FLOW_CHANGE_EXISTING_RESERVATION,
            main.infer_pending_flow_type({"replaceReservationId": "abc"}),
        )
        self.assertEqual(
            main.FLOW_BLOCKED_EXISTING_RESERVATION,
            main.infer_pending_flow_type({"blockedByReservationId": "abc"}),
        )

    def test_blocked_pending_is_not_confirmable(self):
        required_fields = {
            "room": "7202",
            "startTime": "2026-07-08T11:00:00+09:00",
            "duration": 2,
            "eventParticipants": "5",
        }

        self.assertTrue(main.can_confirm_pending({**required_fields, "flowType": main.FLOW_NEW_RESERVATION}))
        self.assertTrue(main.can_confirm_pending({**required_fields, "flowType": main.FLOW_ALTERNATIVE_NEW_RESERVATION}))
        self.assertTrue(main.can_confirm_pending({**required_fields, "flowType": main.FLOW_CHANGE_EXISTING_RESERVATION}))
        self.assertFalse(main.can_confirm_pending({**required_fields, "flowType": main.FLOW_BLOCKED_EXISTING_RESERVATION}))
        self.assertFalse(main.can_confirm_pending({"flowType": main.FLOW_NEW_RESERVATION}))


if __name__ == "__main__":
    unittest.main()
