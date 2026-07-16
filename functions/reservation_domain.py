"""Pure reservation data and pending-flow rules.

This module has no Firestore dependencies. Persistence and workflow handlers stay
in reservation_service.py while the split is performed incrementally.
"""

import re
from datetime import datetime

from reservation_utils import KST, format_korean_time, is_canonical_room_id, parse_korean_time


FLOW_NEW_RESERVATION = "new_reservation"
FLOW_BLOCKED_EXISTING_RESERVATION = "blocked_existing_reservation"
FLOW_ALTERNATIVE_NEW_RESERVATION = "alternative_new_reservation"
FLOW_CHANGE_EXISTING_RESERVATION = "change_existing_reservation"

CONFIRMABLE_PENDING_FLOWS = {
    FLOW_NEW_RESERVATION,
    FLOW_ALTERNATIVE_NEW_RESERVATION,
    FLOW_CHANGE_EXISTING_RESERVATION,
}


def normalize_event_participants(query):
    event_participants_value = query.get("eventParticipants")

    if not event_participants_value and query.get("keywords"):
        person_count = next(
            (
                int(keyword.replace("명", ""))
                for keyword in query.get("keywords", [])
                if (
                    isinstance(keyword, str)
                    and keyword.endswith("명")
                    and keyword[:-1].isdigit()
                )
            ),
            None,
        )
        if person_count:
            event_participants_value = str(person_count)

    if isinstance(event_participants_value, str):
        return event_participants_value.strip()
    return str(event_participants_value or "").strip()


def missing_required_fields(query, fields):
    return [
        field
        for field in fields
        if not query.get(field) or not str(query.get(field)).strip()
    ]


def parse_reservation_start_and_duration(query):
    query["duration"] = int(query["duration"])
    start = datetime.fromisoformat(query["startTime"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=KST)
    return start, query["duration"]


def parse_participants_int(value):
    numeric_part = re.search(r"\d+", str(value or "").strip())
    return int(numeric_part.group()) if numeric_part else 1


def reservation_time_range(data):
    start = data.get("startTimestamp")
    end = data.get("endTimestamp")
    if not start or not hasattr(start, "timestamp"):
        start = parse_korean_time(data.get("startTime"))
    if not end or not hasattr(end, "timestamp"):
        end = parse_korean_time(data.get("endTime"))
    return start, end


def build_reservation_document(query, user_id, owner_uid, start, end):
    if not is_canonical_room_id(query.get("room")):
        raise ValueError("Reservation room must use a canonical four-digit roomID")
    return {
        "documentId": "",
        "roomID": query["room"],
        "startTime": format_korean_time(start),
        "endTime": format_korean_time(end),
        "eventName": query.get("eventName", "추천 예약"),
        "eventDescription": query.get("eventDescription", ""),
        "eventTarget": query.get("eventTarget", ""),
        "eventParticipants": parse_participants_int(query.get("eventParticipants")),
        "status": query.get("status", "대기"),
        "userID": user_id,
        "ownerUid": owner_uid or "",
    }


def infer_pending_flow_type(pending_data):
    flow_type = (pending_data or {}).get("flowType")
    if flow_type:
        return flow_type
    if (pending_data or {}).get("replaceReservationId"):
        return FLOW_CHANGE_EXISTING_RESERVATION
    if (pending_data or {}).get("blockedByReservationId"):
        return FLOW_BLOCKED_EXISTING_RESERVATION
    return FLOW_NEW_RESERVATION


def can_confirm_pending(pending_data):
    pending_data = pending_data or {}
    has_required_reservation_fields = all(
        str(pending_data.get(field) or "").strip()
        for field in ("room", "startTime", "duration", "eventParticipants")
    )
    return (
        infer_pending_flow_type(pending_data) in CONFIRMABLE_PENDING_FLOWS
        and has_required_reservation_fields
    )


def build_pending_reservation_data(
    room,
    start,
    duration,
    event_participants=None,
    owner_uid="",
    event_name=None,
    event_description="",
    event_target="",
    flow_type=FLOW_NEW_RESERVATION,
    replace_reservation_id=None,
    blocked_by_reservation_id=None,
    blocked_by_own_reservation=False,
):
    data = {
        "room": room,
        "startTime": start.isoformat() if isinstance(start, datetime) else start,
        "duration": duration,
        "eventName": event_name or "추천 예약",
        "eventDescription": event_description or "",
        "eventTarget": event_target or "",
        "ownerUid": owner_uid,
        "flowType": flow_type,
    }
    if event_participants is not None:
        data["eventParticipants"] = str(event_participants).strip()
    if replace_reservation_id:
        data["replaceReservationId"] = replace_reservation_id
    if blocked_by_reservation_id:
        data["blockedByReservationId"] = blocked_by_reservation_id
        data["blockedByOwnReservation"] = bool(blocked_by_own_reservation)
    return data
