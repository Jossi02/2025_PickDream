import json

from firebase_functions import https_fn


AI_RESPONSE_SCHEMA_VERSION = 1
AI_RESPONSE_KIND = "assistant_response"


def build_ai_payload(text, title=None, cards=None):
    return {
        "schemaVersion": AI_RESPONSE_SCHEMA_VERSION,
        "kind": AI_RESPONSE_KIND,
        "text": str(text or ""),
        "title": str(title or ""),
        "cards": list(cards or []),
    }


def parse_ai_payload(value):
    if isinstance(value, dict):
        payload = value
    else:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if not isinstance(value, str) or not value.lstrip().startswith("{"):
            return None
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            return None

    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        return None
    return payload


def extract_ai_response_text(value):
    payload = parse_ai_payload(value)
    if payload is not None:
        return payload["text"]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def make_ai_response(text, status=200, query=None, title=None, cards=None):
    if query and query.get("_structuredResponse"):
        payload = build_ai_payload(text, title=title, cards=cards)
        return https_fn.Response(
            json.dumps(payload, ensure_ascii=False),
            status=status,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    return https_fn.Response(text, status=status)


def ai_action(label, message, display_text=None):
    return {
        "label": label,
        "message": message,
        "displayText": display_text or label,
    }


def ai_card(card_type, room_name, description="", start_time="", end_time="", participants=None, actions=None):
    return {
        "type": card_type,
        "roomName": room_name,
        "description": description,
        "startTime": start_time,
        "endTime": end_time,
        "participants": "" if participants is None else str(participants),
        "actions": actions or [],
    }
