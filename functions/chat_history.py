from datetime import datetime, timedelta

from firebase_admin import firestore

from ai_response import extract_ai_response_text, parse_ai_payload
from reservation_utils import KST


CHAT_HISTORY_MAX_MESSAGES = 10
CHAT_HISTORY_RETENTION_DAYS = 30


def normalize_stored_messages(messages):
    normalized = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        normalized_message = dict(message)
        if normalized_message.get("role") == "model" and normalized_message.get("text"):
            legacy_payload = parse_ai_payload(normalized_message["text"])
            normalized_message["text"] = extract_ai_response_text(normalized_message["text"])
            if legacy_payload is not None and not normalized_message.get("response"):
                normalized_message["response"] = legacy_payload
        normalized.append(normalized_message)
    return normalized


def load_chat_history(db, user_id):
    history_ref = db.collection("ChatHistory").document(user_id)
    history_doc = history_ref.get()
    stored_messages = []
    if history_doc.exists:
        messages = history_doc.to_dict().get("messages", [])
        if isinstance(messages, list):
            stored_messages = normalize_stored_messages(messages[-CHAT_HISTORY_MAX_MESSAGES:])

    chat_history = []
    for msg in stored_messages:
        if isinstance(msg, dict) and msg.get("role") in {"user", "model"} and msg.get("text"):
            message_text = (
                extract_ai_response_text(msg["text"])
                if msg["role"] == "model"
                else str(msg["text"])
            )
            chat_history.append({"role": msg["role"], "parts": [{"text": message_text}]})

    return history_ref, stored_messages, chat_history


def build_updated_messages(stored_messages, user_text, model_text):
    model_message = {
        "role": "model",
        "text": extract_ai_response_text(model_text),
    }
    structured_payload = parse_ai_payload(model_text)
    if structured_payload is not None:
        model_message["response"] = structured_payload

    return (
        normalize_stored_messages(stored_messages)
        + [
            {"role": "user", "text": user_text},
            model_message,
        ]
    )[-CHAT_HISTORY_MAX_MESSAGES:]


def save_chat_turn(history_ref, stored_messages, user_text, model_text):
    history_ref.set(
        {
            "messages": build_updated_messages(stored_messages, user_text, model_text),
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "expiresAt": datetime.now(KST) + timedelta(days=CHAT_HISTORY_RETENTION_DAYS),
        },
        merge=True,
    )


def delete_expired_chat_history(db, limit=450):
    now = datetime.now(KST)
    cutoff = now - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)
    expired_docs = list(
        db.collection("ChatHistory")
        .where("expiresAt", "<=", now)
        .limit(limit)
        .stream()
    )
    deleted = 0

    batch = db.batch()
    for doc in expired_docs:
        batch.delete(doc.reference)
        deleted += 1
    if expired_docs:
        batch.commit()

    remaining_limit = max(limit - deleted, 0)
    if remaining_limit <= 0:
        return deleted

    legacy_docs = list(db.collection("ChatHistory").limit(remaining_limit).stream())
    batch = db.batch()
    operations = 0
    for doc in legacy_docs:
        data = doc.to_dict() or {}
        if data.get("expiresAt"):
            continue

        reference_time = data.get("updatedAt") or getattr(doc, "update_time", None)
        if not isinstance(reference_time, datetime):
            continue
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=KST)
        else:
            reference_time = reference_time.astimezone(KST)

        if reference_time <= cutoff:
            batch.delete(doc.reference)
            deleted += 1
        else:
            batch.update(
                doc.reference,
                {"expiresAt": reference_time + timedelta(days=CHAT_HISTORY_RETENTION_DAYS)},
            )
        operations += 1

    if operations:
        batch.commit()
    return deleted
