"""Firestore read operations for reservations.

Write workflows remain in reservation_service.py. Query functions receive their
dependencies explicitly so they stay testable and do not own global clients.
"""

import logging
from datetime import datetime

from reservation_domain import reservation_time_range
from reservation_utils import (
    KST,
    intervals_overlap,
    reservation_room_id,
    room_id_aliases,
    same_room_id,
)


CANCELLED_STATUSES = {"취소", "거절"}


def reservation_documents_for_field(db, field: str, value: str):
    if field != "roomID":
        yield from db.collection("Reservations").where(field, "==", value).stream()
        return

    seen = set()
    for alias in room_id_aliases(value):
        for doc in db.collection("Reservations").where("roomID", "==", alias).stream():
            if doc.id in seen:
                continue
            seen.add(doc.id)
            yield doc


def has_conflict(document_loader, field, value, start, end, exclude_id=None):
    logging.info(
        "[has_conflict] field=%s, value=%s, exclude_id=%s",
        field,
        value,
        exclude_id,
    )
    for doc in document_loader(field, value):
        if exclude_id and doc.id == exclude_id:
            continue

        data = doc.to_dict()
        if data.get("status") in CANCELLED_STATUSES:
            continue

        conflict_start, conflict_end = reservation_time_range(data)
        if not conflict_start or not conflict_end:
            continue

        try:
            if intervals_overlap(start, end, conflict_start, conflict_end):
                return True
        except Exception as error:
            logging.warning(
                "[has_conflict] 날짜 비교 중 오류 무시 (문서 ID: %s): %s",
                doc.id,
                error,
            )
    return False


def find_conflicting_reservation(
    document_loader,
    field,
    value,
    start,
    end,
    exclude_id=None,
):
    for doc in document_loader(field, value):
        if exclude_id and doc.id == exclude_id:
            continue

        data = doc.to_dict()
        if data.get("status") in CANCELLED_STATUSES:
            continue

        conflict_start, conflict_end = reservation_time_range(data)
        if (
            conflict_start
            and conflict_end
            and intervals_overlap(start, end, conflict_start, conflict_end)
        ):
            return doc.id, data
    return None, None


def find_user_reservation(db, user_id, room_id=None, target_start=None):
    now = datetime.now(KST)
    candidates = []
    for doc in db.collection("Reservations").where("userID", "==", user_id).stream():
        data = doc.to_dict()
        if data.get("status") in CANCELLED_STATUSES:
            continue

        document_room_id = str(data.get("roomID") or data.get("room") or "").strip()
        if room_id and not same_room_id(document_room_id, room_id):
            continue

        start, end = reservation_time_range(data)
        if target_start and start and end:
            if not (start <= target_start < end or start.date() == target_start.date()):
                continue

        if start:
            priority = 0 if start >= now else 1
            distance = abs((start - (target_start or now)).total_seconds())
        else:
            priority = 2
            distance = 10**12
        candidates.append((priority, distance, doc.id, data, start, end))

    if not candidates:
        return None, None, None, None

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, document_id, data, start, end = candidates[0]
    return document_id, data, start, end


def list_user_upcoming_reservations(
    db,
    user_id,
    room_label_formatter,
    limit=3,
):
    now = datetime.now(KST)
    rooms_cache = {}
    for doc in db.collection("rooms").stream():
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        rooms_cache[room_id] = room_label_formatter(room_id, data)

    reservations = []
    for doc in db.collection("Reservations").where("userID", "==", user_id).stream():
        data = doc.to_dict()
        if data.get("status") in CANCELLED_STATUSES:
            continue
        start, end = reservation_time_range(data)
        if end and end < now:
            continue
        data["_documentId"] = doc.id
        room_id = str(data.get("roomID") or "")
        room_name = rooms_cache.get(room_id, room_label_formatter(room_id))
        reservations.append((start or datetime.max.replace(tzinfo=KST), room_name, data))

    reservations.sort(key=lambda item: item[0])
    return reservations[:limit]
