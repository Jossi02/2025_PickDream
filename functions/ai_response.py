import json

from firebase_functions import https_fn


def make_ai_response(text, status=200, query=None, title=None, cards=None):
    if query and query.get("_structuredResponse"):
        payload = {
            "text": text,
            "title": title or "",
            "cards": cards or [],
        }
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
