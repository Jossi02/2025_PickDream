import json
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_response import (  # noqa: E402
    AI_RESPONSE_KIND,
    AI_RESPONSE_SCHEMA_VERSION,
    ai_action,
    ai_card,
    build_ai_payload,
    extract_ai_response_text,
    make_ai_response,
    parse_ai_payload,
)
from chat_history import build_updated_messages, normalize_stored_messages  # noqa: E402


class AiResponseContractTest(unittest.TestCase):
    def test_structured_response_uses_versioned_envelope(self):
        response = make_ai_response(
            "예약 내용을 확인해 주세요",
            query={"_structuredResponse": True},
            title="예약 확인",
            cards=[
                ai_card(
                    "confirmation",
                    "7202 강의실",
                    actions=[ai_action("예약 확정", "예약확정")],
                )
            ],
        )

        payload = json.loads(response.data.decode("utf-8"))
        self.assertEqual(AI_RESPONSE_SCHEMA_VERSION, payload["schemaVersion"])
        self.assertEqual(AI_RESPONSE_KIND, payload["kind"])
        self.assertEqual("예약 내용을 확인해 주세요", payload["text"])
        self.assertEqual("confirmation", payload["cards"][0]["type"])

    def test_plain_text_client_remains_backward_compatible(self):
        response = make_ai_response("plain response")
        self.assertEqual("plain response", response.data.decode("utf-8"))

    def test_response_text_extraction_accepts_versioned_and_legacy_payloads(self):
        versioned = json.dumps(build_ai_payload("versioned text"), ensure_ascii=False)
        legacy = json.dumps({"text": "legacy text", "title": "", "cards": []}, ensure_ascii=False)

        self.assertEqual("versioned text", extract_ai_response_text(versioned))
        self.assertEqual("legacy text", extract_ai_response_text(legacy))
        self.assertEqual("plain text", extract_ai_response_text("plain text"))
        self.assertIsNotNone(parse_ai_payload(versioned))

    def test_chat_history_stores_readable_text_and_structured_payload_separately(self):
        payload = build_ai_payload(
            "7202 강의실 예약을 확인해 주세요",
            title="예약 확인",
            cards=[ai_card("confirmation", "7202 강의실")],
        )
        messages = build_updated_messages(
            [],
            "예약해줘",
            json.dumps(payload, ensure_ascii=False),
        )

        model_message = messages[-1]
        self.assertEqual("7202 강의실 예약을 확인해 주세요", model_message["text"])
        self.assertEqual(AI_RESPONSE_SCHEMA_VERSION, model_message["response"]["schemaVersion"])
        self.assertEqual("7202 강의실", model_message["response"]["cards"][0]["roomName"])

    def test_legacy_chat_history_json_is_migrated_on_next_save(self):
        legacy_payload = json.dumps(
            {"text": "기존 응답", "title": "기존 카드", "cards": []},
            ensure_ascii=False,
        )
        normalized = normalize_stored_messages(
            [{"role": "model", "text": legacy_payload}]
        )

        self.assertEqual("기존 응답", normalized[0]["text"])
        self.assertEqual("기존 카드", normalized[0]["response"]["title"])


if __name__ == "__main__":
    unittest.main()
