from datetime import datetime, timedelta

from firebase_admin import firestore

from reservation_utils import KST


CHAT_HISTORY_MAX_MESSAGES = 10
CHAT_HISTORY_RETENTION_DAYS = 30


def load_chat_history(db, user_id):
    history_ref = db.collection("ChatHistory").document(user_id)
    history_doc = history_ref.get()
    stored_messages = []
    if history_doc.exists:
        messages = history_doc.to_dict().get("messages", [])
        if isinstance(messages, list):
            stored_messages = messages[-CHAT_HISTORY_MAX_MESSAGES:]

    chat_history = []
    for msg in stored_messages:
        if isinstance(msg, dict) and msg.get("role") in {"user", "model"} and msg.get("text"):
            chat_history.append({"role": msg["role"], "parts": [{"text": str(msg["text"])}]})

    return history_ref, stored_messages, chat_history


def build_updated_messages(stored_messages, user_text, model_text):
    return (
        stored_messages
        + [
            {"role": "user", "text": user_text},
            {"role": "model", "text": model_text},
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
