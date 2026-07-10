import logging
import re
from datetime import datetime, timedelta

from firebase_admin import firestore
from firebase_functions import https_fn

from ai_intents import recover_reserve_fields_from_text
from ai_response import ai_action, ai_card, make_ai_response
from room_service import display_room_label, find_available_rooms, find_room

from reservation_utils import (
    KST,
    format_korean_time,
    intervals_overlap,
    parse_korean_time,
    reservation_room_id,
    room_id_aliases,
    same_room_id,
)


db = None
_db = None
_display_room_label = None


def configure_reservation_service(db_client, room_label_formatter=None):
    global db, _db, _display_room_label
    db = db_client
    _db = db_client
    _display_room_label = room_label_formatter


def _require_db():
    if _db is None:
        raise RuntimeError("reservation_service is not configured")
    return _db


def _format_room_label(room_id, room_data=None):
    if _display_room_label is not None:
        return _display_room_label(room_id, room_data)
    canonical_id = reservation_room_id(str(room_id or ""), room_data or {})
    return f"{canonical_id} 강의실" if canonical_id else "강의실"


def _reservation_documents_for_field(field: str, value: str):
    db = _require_db()
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


def has_conflict(field: str, value: str, start, end, exclude_id: str = None):
    # 인덱스 문제와 안드로이드 앱의 Extra Fields 크래시 문제를 해결하기 위해,
    # startTimestamp/endTimestamp 필드 대신 문자열 startTime/endTime을 파싱하여 메모리에서 모두 비교합니다.
    conflicts = _reservation_documents_for_field(field, value)

    logging.info("[has_conflict] field=%s, value=%s, exclude_id=%s", field, value, exclude_id)

    for doc in conflicts:
        if exclude_id and doc.id == exclude_id:
            continue

        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue

        c_start = data.get("startTimestamp")
        c_end = data.get("endTimestamp")

        # 만약 Timestamp 객체가 없다면 문자열에서 파싱
        if not c_start or not hasattr(c_start, "timestamp"):
            c_start = parse_korean_time(data.get("startTime"))
        if not c_end or not hasattr(c_end, "timestamp"):
            c_end = parse_korean_time(data.get("endTime"))

        if not c_start or not c_end:
            continue

        try:
            # 겹치는 조건: 기존 예약의 시작시간이 새 예약의 종료시간보다 앞서고, 기존 예약의 종료시간이 새 예약의 시작시간보다 뒤일 때
            if intervals_overlap(start, end, c_start, c_end):
                return True
        except Exception as e:
            logging.warning("[has_conflict] 날짜 비교 중 오류 무시 (문서 ID: %s): %s", doc.id, e)
            continue

    return False


def find_conflicting_reservation(field: str, value: str, start, end, exclude_id: str = None):
    conflicts = _reservation_documents_for_field(field, value)
    for doc in conflicts:
        if exclude_id and doc.id == exclude_id:
            continue

        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue

        c_start = data.get("startTimestamp")
        c_end = data.get("endTimestamp")
        if not c_start or not hasattr(c_start, "timestamp"):
            c_start = parse_korean_time(data.get("startTime"))
        if not c_end or not hasattr(c_end, "timestamp"):
            c_end = parse_korean_time(data.get("endTime"))

        if c_start and c_end and intervals_overlap(start, end, c_start, c_end):
            return doc.id, data
    return None, None


def reservation_time_range(data):
    start = data.get("startTimestamp")
    end = data.get("endTimestamp")
    if not start or not hasattr(start, "timestamp"):
        start = parse_korean_time(data.get("startTime"))
    if not end or not hasattr(end, "timestamp"):
        end = parse_korean_time(data.get("endTime"))
    return start, end


def find_user_reservation(userID, room_id=None, target_start=None):
    db = _require_db()
    now = datetime.now(KST)
    candidates = []
    for doc in db.collection("Reservations").where("userID", "==", userID).stream():
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue

        doc_room_id = str(data.get("roomID") or data.get("room") or "").strip()
        if room_id and not same_room_id(doc_room_id, room_id):
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
    _, _, doc_id, data, start, end = candidates[0]
    return doc_id, data, start, end


def list_user_upcoming_reservations(userID, limit=3):
    db = _require_db()
    now = datetime.now(KST)
    rooms_cache = {}
    for doc in db.collection("rooms").stream():
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        rooms_cache[room_id] = _format_room_label(room_id, data)

    reservations = []
    for doc in db.collection("Reservations").where("userID", "==", userID).stream():
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue
        start, end = reservation_time_range(data)
        if end and end < now:
            continue
        data["_documentId"] = doc.id
        room_id = str(data.get("roomID") or "")
        room_name = rooms_cache.get(room_id, _format_room_label(room_id))
        reservations.append((start or datetime.max.replace(tzinfo=KST), room_name, data))

    reservations.sort(key=lambda item: item[0])
    return reservations[:limit]


def normalize_event_participants(query):
    event_participants_value = query.get("eventParticipants")

    if not event_participants_value and query.get("keywords"):
        person_count = next(
            (
                int(k.replace("명", ""))
                for k in query.get("keywords", [])
                if isinstance(k, str) and k.endswith("명") and k[:-1].isdigit()
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


def build_reservation_document(query, userID, owner_uid, start, end):
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
        "userID": userID,
        "ownerUid": owner_uid or "",
    }

# Reservation flow constants and write handlers moved from main.py.
FLOW_NEW_RESERVATION = "new_reservation"
FLOW_BLOCKED_EXISTING_RESERVATION = "blocked_existing_reservation"
FLOW_ALTERNATIVE_NEW_RESERVATION = "alternative_new_reservation"
FLOW_CHANGE_EXISTING_RESERVATION = "change_existing_reservation"

CONFIRMABLE_PENDING_FLOWS = {
    FLOW_NEW_RESERVATION,
    FLOW_ALTERNATIVE_NEW_RESERVATION,
    FLOW_CHANGE_EXISTING_RESERVATION,
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
        "eventName": event_name or "\ucd94\ucc9c \uc608\uc57d",
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

def suggest_alternative_room_response(
    original_room_name,
    start,
    end,
    duration,
    event_participants,
    owner_uid,
    userID,
    exclude_room_ids=None,
    replace_reservation_id=None,
    structured=False,
):
    numeric_part = re.search(r"\d+", str(event_participants or ""))
    person_count = int(numeric_part.group()) if numeric_part else 0
    alternatives = find_available_rooms(
        start,
        end,
        person_count=person_count,
        exclude_room_ids=exclude_room_ids,
    )
    if not alternatives:
        return https_fn.Response(
            f"{original_room_name}\uc740 \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc774\ubbf8 \uc608\uc57d\ub418\uc5b4 \uc788\uace0, "
            "\uac19\uc740 \uc2dc\uac04\uc5d0 \uc870\uac74\uc5d0 \ub9de\ub294 \ub2e4\ub978 \uac15\uc758\uc2e4\ub3c4 \ucc3e\uc9c0 \ubabb\ud588\uc5b4\uc694. "
            "\ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.",
            status=409,
        )

    _, alt_room_id, _, alt_room_data = alternatives[0]
    alt_room_name = display_room_label(alt_room_id, alt_room_data)
    pending_data = build_pending_reservation_data(
        room=alt_room_id,
        start=start,
        duration=duration,
        event_participants=event_participants,
        owner_uid=owner_uid,
        flow_type=(
            FLOW_CHANGE_EXISTING_RESERVATION
            if replace_reservation_id
            else FLOW_ALTERNATIVE_NEW_RESERVATION
        ),
        replace_reservation_id=replace_reservation_id,
    )
    db.collection("PendingReservations").document(userID).set(pending_data)
    action_hint = (
        "\uae30\uc874 \uc608\uc57d\uc744 \uc774 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd"
        if replace_reservation_id
        else "\uc774 \uac15\uc758\uc2e4\ub85c \uc608\uc57d"
    )
    response_text = (
        f"{original_room_name}\uc740 \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc774\ubbf8 \uc608\uc57d\ub418\uc5b4 \uc788\uc5b4\uc694.\n\n"
        f"\ub300\uc2e0 {alt_room_name}\uc740 \uac19\uc740 \uc2dc\uac04\uc5d0 \uc608\uc57d \uac00\ub2a5\ud574\uc694.\n"
        f"\uc2dc\uac04: {format_korean_time(start)} ~ {format_korean_time(end)}\n"
        f"\uc778\uc6d0: {pending_data['eventParticipants']}\n\n"
        f"{action_hint}\ud558\uc2dc\ub824\uba74 '\uc608\uc57d \ud655\uc815'\uc774\ub77c\uace0 \uc785\ub825\ud574 \uc8fc\uc138\uc694."
    )
    return make_ai_response(
        response_text,
        query={"_structuredResponse": structured},
        title="대체 강의실 제안",
        cards=[
            ai_card(
                "alternative",
                alt_room_name,
                start_time=format_korean_time(start),
                end_time=format_korean_time(end),
                participants=pending_data["eventParticipants"],
                actions=[ai_action("예약 확정", "예약확정", "예약확정")],
            )
        ],
    )

def handle_reserve(query, userID):
    try:
        logging.info(f"[handle_reserve] input query: {query}")
        owner_uid = query.pop("ownerUid", "")
        raw_user_input = (
            query.pop("rawUserInput", "")
            or query.pop("originalUserInput", "")
            or query.pop("message", "")
            or ""
        )
        query["userID"] = userID
        recover_reserve_fields_from_text(query, raw_user_input)

        room_raw = query.get("room")
        room_id, room_data = find_room(room_raw)
        allow_alternative_room = bool(query.pop("allowAlternativeRoom", False))
        explicit_change_reservation = bool(query.pop("explicitChangeReservation", False))

        pending = db.collection("PendingReservations").document(userID).get()
        if pending.exists:
            pending_data = pending.to_dict()
            if allow_alternative_room and pending_data.get("blockedByReservationId"):
                blocked_by_own_reservation = bool(pending_data.get("blockedByOwnReservation"))
                pending_room_id = pending_data.get("room")
                _, pending_room_data = find_room(pending_room_id)
                pending_room_name = display_room_label(pending_room_id, pending_room_data)
                if blocked_by_own_reservation and not explicit_change_reservation:
                    response_text = (
                        f"\uc774\ubbf8 {pending_room_name}\uc744(\ub97c) \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc608\uc57d\ud574\ub450\uc168\uc5b4\uc694.\n\n"
                        "\uc0c8 \uc608\uc57d\uc744 \ucd94\uac00\ub85c \ub9cc\ub4e4 \uc218\ub294 \uc5c6\uc5b4\uc694. "
                        "\ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.\n"
                        "\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubc14\uafb8\ub824\uba74 "
                        "'\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918'\ub77c\uace0 \uc785\ub825\ud574 \uc8fc\uc138\uc694."
                    )
                    return make_ai_response(
                        response_text,
                        status=409,
                        query=query,
                        title="예약 충돌 안내",
                        cards=[
                            ai_card(
                                "own_conflict",
                                pending_room_name,
                                description="같은 시간대에 예약하신 기록이 있어요.",
                                actions=[
                                    ai_action(
                                        "기존 예약 변경",
                                        "기존 예약을 다른 강의실로 변경해줘",
                                        "기존 예약 변경",
                                    )
                                ],
                            )
                        ],
                    )
                try:
                    pending_start = datetime.fromisoformat(str(pending_data.get("startTime")))
                    if pending_start.tzinfo is None:
                        pending_start = pending_start.replace(tzinfo=KST)
                    pending_duration = int(pending_data.get("duration") or query.get("duration") or 2)
                    pending_end = pending_start + timedelta(hours=pending_duration)
                    return suggest_alternative_room_response(
                        pending_room_name,
                        pending_start,
                        pending_end,
                        pending_duration,
                        query.get("eventParticipants") or pending_data.get("eventParticipants"),
                        owner_uid or pending_data.get("ownerUid", ""),
                        userID,
                        exclude_room_ids={pending_room_id},
                        replace_reservation_id=(
                            pending_data.get("blockedByReservationId")
                            if blocked_by_own_reservation and explicit_change_reservation
                            else None
                        ),
                        structured=query.get("_structuredResponse", False),
                    )
                except Exception as e:
                    logging.warning("[handle_reserve] pending alternative suggestion failed: %s", e)
                return https_fn.Response(
                    f"이미 {pending_room_name}을(를) 해당 시간에 예약해두셨어요.\n\n"
                    "새 예약을 추가로 만들 수는 없어요. 다른 시간대를 선택해 주세요.\n"
                    "기존 예약을 다른 강의실로 바꾸려면 '기존 예약을 다른 강의실로 변경해줘'라고 입력해 주세요.",
                    status=409,
                )
            if not room_id and not room_raw and not allow_alternative_room:
                room_id, room_data = find_room(pending_data.get("room"))
            for field in ("startTime", "duration", "eventName", "eventParticipants"):
                query[field] = query.get(field) or pending_data.get(field)
            if allow_alternative_room:
                query["room"] = ""
        query["duration"] = query.get("duration") or 2

        if not room_id and query.get("room"):
            return https_fn.Response("해당 강의실 정보를 확인할 수 없어요.", status=400)
            
        if allow_alternative_room and not room_id:
            query["room"] = ""
        else:
            query["room"] = reservation_room_id(room_id, room_data) if room_data else room_id

        query["eventName"] = query.get("eventName") or "추천 예약"
        query["eventDescription"] = query.get("eventDescription") or ""
        query["eventTarget"] = query.get("eventTarget") or ""
        query["eventParticipants"] = normalize_event_participants(query)
        query["status"] = "대기"
        recover_reserve_fields_from_text(query, raw_user_input)
        query["eventParticipants"] = normalize_event_participants(query)

        has_room_and_time = bool(query.get("room")) and bool(query.get("startTime"))
        missing_participants_only = (
            has_room_and_time
            and bool(query.get("duration"))
            and not query.get("eventParticipants")
        )
        if missing_participants_only:
            try:
                preview_duration = int(query.get("duration") or 2)
                preview_start = datetime.fromisoformat(str(query["startTime"]))
                if preview_start.tzinfo is None:
                    preview_start = preview_start.replace(tzinfo=KST)
                preview_end = preview_start + timedelta(hours=preview_duration)
                preview_room_id = str(query["room"])
                preview_room_name = display_room_label(preview_room_id, room_data)

                user_conflict_id, user_conflict_data = find_conflicting_reservation(
                    "userID",
                    userID,
                    preview_start,
                    preview_end,
                )
                if user_conflict_id:
                    conflict_room_id = user_conflict_data.get("roomID") or user_conflict_data.get("room")
                    _, conflict_room_data = find_room(conflict_room_id)
                    conflict_room_name = display_room_label(conflict_room_id, conflict_room_data)
                    db.collection("PendingReservations").document(userID).set(
                        {
                            "room": conflict_room_id,
                            "startTime": preview_start.isoformat(),
                            "duration": preview_duration,
                            "eventName": query.get("eventName", "추천 예약"),
                            "eventDescription": query.get("eventDescription", ""),
                            "eventTarget": query.get("eventTarget", ""),
                            "ownerUid": owner_uid,
                            "blockedByReservationId": user_conflict_id,
                            "blockedByOwnReservation": True,
                            "flowType": FLOW_BLOCKED_EXISTING_RESERVATION,
                        },
                        merge=True,
                    )
                    return https_fn.Response(
                        f"이미 {conflict_room_name}을(를) 해당 시간에 예약해두셨어요. "
                        "새 예약을 만들려면 다른 시간대를 선택해 주세요. "
                        "기존 예약을 바꾸려는 목적이라면 '기존 예약을 다른 강의실로 변경해줘'라고 말해 주세요.",
                        status=409,
                    )

                if has_conflict("roomID", preview_room_id, preview_start, preview_end):
                    db.collection("PendingReservations").document(userID).set(
                        {
                            "room": preview_room_id,
                            "startTime": preview_start.isoformat(),
                            "duration": preview_duration,
                            "eventName": query.get("eventName", "추천 예약"),
                            "eventDescription": query.get("eventDescription", ""),
                            "eventTarget": query.get("eventTarget", ""),
                            "ownerUid": owner_uid,
                            "flowType": FLOW_BLOCKED_EXISTING_RESERVATION,
                        },
                        merge=True,
                    )
                    return https_fn.Response(
                        f"{preview_room_name}은 해당 시간에 이미 예약되어 있어요.\n"
                        "다른 강의실을 찾아드릴 수 있어요. 원하시면 인원 수와 함께 '다른 강의실로 해줘'라고 말해 주세요.",
                        status=409,
                    )
            except Exception as e:
                logging.warning("[handle_reserve] early conflict check skipped: %s", e)

        missing_details = missing_required_fields(query, ("startTime", "duration", "eventParticipants"))
        if missing_details:
            logging.warning(
                "[handle_reserve] missing_details=%s raw=%r query=%s",
                missing_details,
                raw_user_input[:200],
                {
                    "room": query.get("room"),
                    "startTime": query.get("startTime"),
                    "duration": query.get("duration"),
                    "eventParticipants": query.get("eventParticipants"),
                    "needsConfirmation": query.get("needsConfirmation"),
                    "flowType": query.get("flowType"),
                },
            )
            query["flowType"] = query.get("flowType") or FLOW_NEW_RESERVATION
            db.collection("PendingReservations").document(userID).set(query, merge=True)
            friendly_names = {
                "startTime": "시작 시간",
                "duration": "이용 시간",
                "eventParticipants": "이용 인원 수",
            }
            readable = ", ".join(friendly_names[field] for field in missing_details)
            return https_fn.Response(f"다음 정보가 필요해요: {readable}", status=400)

        try:
            start, duration = parse_reservation_start_and_duration(query)
        except Exception as e:
            logging.exception(f"[handle_reserve] 시간 파싱 실패: {query.get('startTime')}")
            return https_fn.Response("시작 시간이 올바른 형식이 아니에요. (예: 내일 오후 3시)", status=400)

        if duration < 1 or duration > 6:
            return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

        now = datetime.now(KST)
        if start < now:
            return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)

        end = start + timedelta(hours=duration)

        # 자동으로 빈 강의실 찾기 로직
        if not query.get("room") or str(query.get("room")).strip() == "":
            try:
                person_count = int(re.search(r'\d+', str(query.get("eventParticipants", "0"))).group())
            except:
                person_count = 0
                
            matched = find_available_rooms(start, end, person_count=person_count)
            
            if not matched:
                return https_fn.Response("해당 시간에 원하시는 인원을 수용할 수 있는 빈 강의실이 없습니다 😥", status=409)
            
            # 수용 인원이 가장 꼭 맞는 방 선택 (오름차순)
            matched.sort()
            _, best_room_id, _, best_r_data = matched[0]
            query["room"] = best_room_id
            room_data = best_r_data

        required_fields = ["room", "startTime", "duration", "userID", "eventParticipants", "ownerUid"]
        query["ownerUid"] = owner_uid
        missing = missing_required_fields(query, required_fields)
        if missing:
            query["flowType"] = query.get("flowType") or FLOW_NEW_RESERVATION
            db.collection("PendingReservations").document(userID).set(query, merge=True)
            friendly_names = {
                "room": "강의실",
                "startTime": "시작 시간",
                "duration": "이용 시간",
                "userID": "사용자 정보",
                "eventParticipants": "이용 인원 수",
                "ownerUid": "사용자 인증 정보",
            }
            readable = ", ".join(friendly_names.get(f, f) for f in missing)
            return https_fn.Response(f"다음 정보가 필요해요: {readable}", status=400)

        pending_flow_type = infer_pending_flow_type(query)
        if pending_flow_type == FLOW_CHANGE_EXISTING_RESERVATION:
            replace_reservation_id = query.get("replaceReservationId")
        else:
            # A fresh reservation must never inherit a replacement target from
            # an older pending change flow.
            query.pop("replaceReservationId", None)
            replace_reservation_id = None
        user_conflict_id, user_conflict_data = find_conflicting_reservation(
            "userID",
            userID,
            start,
            end,
            exclude_id=replace_reservation_id,
        )
        if user_conflict_id:
            conflict_room_id = user_conflict_data.get("roomID") or user_conflict_data.get("room")
            _, conflict_room_data = find_room(conflict_room_id)
            conflict_room_name = display_room_label(conflict_room_id, conflict_room_data)
            if allow_alternative_room:
                if not explicit_change_reservation:
                    db.collection("PendingReservations").document(userID).set(
                        build_pending_reservation_data(
                            room=conflict_room_id,
                            start=start,
                            duration=query["duration"],
                            event_participants=query.get("eventParticipants"),
                            event_name=query.get("eventName"),
                            event_description=query.get("eventDescription", ""),
                            event_target=query.get("eventTarget", ""),
                            owner_uid=owner_uid,
                            flow_type=FLOW_BLOCKED_EXISTING_RESERVATION,
                            blocked_by_reservation_id=user_conflict_id,
                            blocked_by_own_reservation=True,
                        ),
                        merge=True,
                    )
                    response_text = (
                        f"\uc774\ubbf8 {conflict_room_name}\uc744(\ub97c) \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc608\uc57d\ud574\ub450\uc168\uc5b4\uc694.\n\n"
                        "\uc0c8 \uc608\uc57d\uc744 \ucd94\uac00\ub85c \ub9cc\ub4e4 \uc218\ub294 \uc5c6\uc5b4\uc694. "
                        "\ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.\n"
                        "\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubc14\uafb8\ub824\uba74 "
                        "'\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918'\ub77c\uace0 \uc785\ub825\ud574 \uc8fc\uc138\uc694."
                    )
                    return make_ai_response(
                        response_text,
                        status=409,
                        query=query,
                        title="예약 충돌 안내",
                        cards=[
                            ai_card(
                                "own_conflict",
                                conflict_room_name,
                                description="같은 시간대에 예약하신 기록이 있어요.",
                                actions=[
                                    ai_action(
                                        "기존 예약 변경",
                                        "기존 예약을 다른 강의실로 변경해줘",
                                        "기존 예약 변경",
                                    )
                                ],
                            )
                        ],
                    )
                return suggest_alternative_room_response(
                    conflict_room_name,
                    start,
                    end,
                    query["duration"],
                    query.get("eventParticipants"),
                    owner_uid,
                    userID,
                    exclude_room_ids={conflict_room_id},
                    replace_reservation_id=(
                        user_conflict_id if explicit_change_reservation else None
                    ),
                    structured=query.get("_structuredResponse", False),
                )
            db.collection("PendingReservations").document(userID).set(
                {
                    "room": conflict_room_id,
                    "startTime": start.isoformat(),
                    "duration": query["duration"],
                    "eventName": query.get("eventName", "\ucd94\ucc9c \uc608\uc57d"),
                    "eventDescription": query.get("eventDescription", ""),
                    "eventTarget": query.get("eventTarget", ""),
                    "eventParticipants": str(query.get("eventParticipants", "")).strip(),
                    "ownerUid": owner_uid,
                    "blockedByReservationId": user_conflict_id,
                    "blockedByOwnReservation": True,
                    "flowType": FLOW_BLOCKED_EXISTING_RESERVATION,
                },
                merge=True,
            )
            response_text = (
                f"\uc774\ubbf8 {conflict_room_name}\uc744(\ub97c) \ud574\ub2f9 \uc2dc\uac04\uc5d0 \uc608\uc57d\ud574\ub450\uc168\uc5b4\uc694. "
                "\uc0c8 \uc608\uc57d\uc744 \ub9cc\ub4e4\ub824\uba74 \ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694. "
                "\uae30\uc874 \uc608\uc57d\uc744 \ubc14\uafb8\ub824\ub294 \ubaa9\uc801\uc774\ub77c\uba74 '\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918'\ub77c\uace0 \ub9d0\ud574 \uc8fc\uc138\uc694."
            )
            return make_ai_response(
                response_text,
                status=409,
                query=query,
                title="예약 충돌 안내",
                cards=[
                    ai_card(
                        "own_conflict",
                        conflict_room_name,
                        description="같은 시간대에 예약하신 기록이 있어요.",
                        actions=[
                            ai_action(
                                "기존 예약 변경",
                                "기존 예약을 다른 강의실로 변경해줘",
                                "기존 예약 변경",
                            )
                        ],
                    )
                ],
            )

        _, room_data = find_room(query["room"])
        if has_conflict("roomID", query["room"], start, end):
            room_name = display_room_label(query["room"], room_data)
            replace_room_conflict_id, replace_room_conflict_data = find_conflicting_reservation(
                "userID",
                userID,
                start,
                end,
            )
            if replace_room_conflict_id and not explicit_change_reservation:
                existing_room_id = (
                    replace_room_conflict_data.get("roomID")
                    or replace_room_conflict_data.get("room")
                    or ""
                )
                _, existing_room_data = find_room(existing_room_id)
                existing_room_name = display_room_label(existing_room_id, existing_room_data)
                db.collection("PendingReservations").document(userID).set(
                    build_pending_reservation_data(
                        room=existing_room_id,
                        start=start,
                        duration=query["duration"],
                        event_participants=query.get("eventParticipants"),
                        event_name=query.get("eventName"),
                        event_description=query.get("eventDescription", ""),
                        event_target=query.get("eventTarget", ""),
                        owner_uid=owner_uid,
                        flow_type=FLOW_BLOCKED_EXISTING_RESERVATION,
                        blocked_by_reservation_id=replace_room_conflict_id,
                        blocked_by_own_reservation=True,
                    ),
                    merge=True,
                )
                response_text = (
                    f"{room_name}은 해당 시간에 이미 예약되어 있어요.\n\n"
                    f"그리고 같은 시간대에 이미 {existing_room_name}을(를) 예약해두셔서 "
                    "새 예약을 추가로 만들 수는 없어요. "
                    "다른 시간대를 선택해 주세요.\n"
                    "기존 예약을 다른 강의실로 바꾸려면 '기존 예약을 다른 강의실로 변경해줘'라고 입력해 주세요."
                )
                return make_ai_response(
                    response_text,
                    status=409,
                    query=query,
                    title="예약 충돌 안내",
                    cards=[
                        ai_card(
                            "own_conflict",
                            room_name,
                            description="같은 시간대에 예약하신 기록이 있어요.",
                            actions=[
                                ai_action(
                                    "기존 예약 변경",
                                    "기존 예약을 다른 강의실로 변경해줘",
                                    "기존 예약 변경",
                                )
                            ],
                        )
                    ],
                )
            return suggest_alternative_room_response(
                room_name,
                start,
                end,
                query["duration"],
                query.get("eventParticipants"),
                owner_uid,
                userID,
                exclude_room_ids={query["room"]},
                replace_reservation_id=(
                    replace_room_conflict_id if explicit_change_reservation else None
                ),
                structured=query.get("_structuredResponse", False),
            )

        room_name = display_room_label(query["room"], room_data)
        if query.pop("needsConfirmation", False):
            pending_data = {
                "room": query["room"],
                "startTime": start.isoformat(),
                "duration": query["duration"],
                "eventName": query.get("eventName", "추천 예약"),
                "eventDescription": query.get("eventDescription", ""),
                "eventTarget": query.get("eventTarget", ""),
                "eventParticipants": str(query.get("eventParticipants", "")).strip(),
                "ownerUid": owner_uid,
                "flowType": FLOW_NEW_RESERVATION,
            }
            if query.get("replaceReservationId"):
                pending_data["replaceReservationId"] = query["replaceReservationId"]
                pending_data["flowType"] = FLOW_CHANGE_EXISTING_RESERVATION
            # This is a complete confirmation proposal. Replacing the pending
            # document prevents stale change/conflict metadata from surviving.
            db.collection("PendingReservations").document(userID).set(pending_data)
            response_text = (
                "예약 내용을 확인해 주세요 😊\n\n"
                f"강의실: {room_name}\n"
                f"시간: {format_korean_time(start)} ~ {format_korean_time(end)}\n"
                f"인원: {pending_data['eventParticipants']}\n\n"
                "맞다면 '예약 확정'이라고 입력해 주세요."
            )
            return make_ai_response(
                response_text,
                query=query,
                title="예약 내용을 확인해 주세요",
                cards=[
                    ai_card(
                        "confirmation",
                        room_name,
                        start_time=format_korean_time(start),
                        end_time=format_korean_time(end),
                        participants=pending_data["eventParticipants"],
                        actions=[ai_action("예약 확정", "예약확정", "예약확정")],
                    )
                ],
            )

        try:
            res_doc = build_reservation_document(query, userID, owner_uid, start, end)
            if replace_reservation_id:
                update_doc = dict(res_doc)
                update_doc["startTimestamp"] = firestore.DELETE_FIELD
                update_doc["endTimestamp"] = firestore.DELETE_FIELD
                db.collection("Reservations").document(replace_reservation_id).update(update_doc)
                doc_ref = (None, type("_DocRef", (), {"id": replace_reservation_id})())
            else:
                doc_ref = db.collection("Reservations").add(res_doc)
        except Exception as e:
            logging.exception("[handle_reserve] 예약 저장 실패")
            return https_fn.Response("예약 저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)

        try:
            db.collection("PendingReservations").document(userID).delete()
        except Exception as e:
            logging.warning(f"[handle_reserve] Pending 삭제 실패: {e}")

        logging.info(f"[handle_reserve] 예약 성공: {doc_ref[1].id}")
        if replace_reservation_id:
            return https_fn.Response(f"{room_name}로 예약이 변경되었습니다 ✅", status=200)
        return https_fn.Response(f"{room_name}이 예약되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_reserve] 최상위 예외 발생")
        return https_fn.Response("예약 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)


def handle_confirm_reservation(query, userID):
    pending_ref = db.collection("PendingReservations").document(userID)
    pending = pending_ref.get()
    if not pending.exists:
        return https_fn.Response("확정할 예약 내용이 없어요. 먼저 예약할 시간과 인원을 알려 주세요.", status=400)

    pending_data = pending.to_dict()
    if not can_confirm_pending(pending_data):
        return https_fn.Response(
            "\ud655\uc815\ud560 \uc608\uc57d \uc81c\uc548\uc774 \uc544\ub2c8\uc5d0\uc694. "
            "\uc0c8 \uc608\uc57d\uc744 \ub9cc\ub4e4\ub824\uba74 \ub2e4\ub978 \uc2dc\uac04\ub300\ub97c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694. "
            "\uae30\uc874 \uc608\uc57d\uc744 \ubc14\uafb8\ub824\uba74 '\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918'\ub77c\uace0 \uc785\ub825\ud574 \uc8fc\uc138\uc694.",
            status=409,
        )
    pending_data["ownerUid"] = query.get("ownerUid", pending_data.get("ownerUid", ""))
    pending_data["_structuredResponse"] = bool(query.get("_structuredResponse"))
    pending_data["confirmed"] = True
    pending_data.pop("needsConfirmation", None)
    flow_type = infer_pending_flow_type(pending_data)
    if flow_type != FLOW_CHANGE_EXISTING_RESERVATION:
        pending_data.pop("replaceReservationId", None)
    else:
        replace_reservation_id = str(pending_data.get("replaceReservationId") or "").strip()
        replacement_target = (
            db.collection("Reservations").document(replace_reservation_id).get()
            if replace_reservation_id
            else None
        )
        if not replacement_target or not replacement_target.exists:
            pending_ref.delete()
            return https_fn.Response(
                "변경할 기존 예약을 찾을 수 없어요. 예약 내역을 다시 확인해 주세요.",
                status=409,
            )
    return handle_reserve(pending_data, userID)



def handle_cancel_reservation(query, userID):
    try:
        target_room_id, target_room_data = find_room(query.get("room"))
        target_reservation_room_id = (
            reservation_room_id(target_room_id, target_room_data)
            if target_room_id and target_room_data
            else None
        )
        target_start = None
        if query.get("startTime"):
            try:
                target_start = datetime.fromisoformat(str(query.get("startTime")))
                if target_start.tzinfo is None:
                    target_start = target_start.replace(tzinfo=KST)
            except (TypeError, ValueError):
                target_start = None
        logging.info(
            "[handle_cancel_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        if not target_reservation_room_id and not target_start and not query.get("forceClosest"):
            candidates = list_user_upcoming_reservations(userID, limit=5)
            if not candidates:
                return https_fn.Response("취소할 예약이 없습니다.", status=404)

            lines = []
            for _, room_name, data in candidates:
                start_text = data.get("startTime", "?")
                end_text = data.get("endTime", "?")
                participants = data.get("eventParticipants")
                participant_text = f" / {participants}명" if participants else ""
                lines.append(f"- {room_name}: {start_text} ~ {end_text}{participant_text}")

            return https_fn.Response(
                "취소할 예약을 선택해 주세요:\n" + "\n".join(lines),
                status=200,
            )

        res_id, res_data, _, _ = find_user_reservation(
            userID,
            room_id=target_reservation_room_id,
            target_start=target_start,
        )
        if not res_id:
            return https_fn.Response("취소할 예약이 없습니다.", status=404)

        cancelled_room_id = res_data.get("roomID")
        _, cancelled_room_data = find_room(cancelled_room_id)
        cancelled_room_name = display_room_label(cancelled_room_id, cancelled_room_data)
        db.collection("Reservations").document(res_id).delete()

        return https_fn.Response(f"{cancelled_room_name} 예약이 취소되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_cancel_reservation] 예외 발생")
        return https_fn.Response("예약 취소 중 오류가 발생했어요. 로그를 확인해주세요.", status=500)


def handle_change_reservation_selection(query, userID):
    candidates = list_user_upcoming_reservations(userID, limit=5)
    if not candidates:
        return https_fn.Response("변경할 예약이 없습니다.", status=404)

    requested_changes = {
        "requestedNewRoom": query.get("newRoom"),
        "requestedStartTime": query.get("startTime"),
        "requestedDuration": query.get("duration"),
        "requestedEventParticipants": query.get("eventParticipants"),
    }
    pending_data = {
        "flowType": FLOW_CHANGE_EXISTING_RESERVATION,
        "awaitingReservationSelection": True,
        "ownerUid": query.get("ownerUid", ""),
        **{key: value for key, value in requested_changes.items() if value not in (None, "")},
    }
    db.collection("PendingReservations").document(userID).set(pending_data)

    cards = []
    lines = []
    for _, room_name, data in candidates:
        document_id = str(data.get("_documentId") or "").strip()
        if not document_id:
            continue
        start, end = reservation_time_range(data)
        start_text = data.get("startTime", "?")
        end_text = data.get("endTime", "?")
        participants = data.get("eventParticipants")
        participant_text = f" / {participants}명" if participants else ""
        lines.append(f"- {room_name}: {start_text} ~ {end_text}{participant_text}")
        cards.append(
            ai_card(
                "change_selection",
                room_name,
                start_time=format_korean_time(start) if start else start_text,
                end_time=format_korean_time(end) if end else end_text,
                participants=participants,
                actions=[
                    ai_action(
                        "예약 변경",
                        f"예약 변경 대상 선택::{document_id}",
                        "예약 변경",
                    )
                ],
            )
        )

    if not cards:
        return https_fn.Response("변경할 예약이 없습니다.", status=404)

    response_text = "변경할 예약을 선택해 주세요:\n" + "\n".join(lines)
    return make_ai_response(
        response_text,
        query=query,
        title="변경할 예약을 선택해 주세요",
        cards=cards,
    )


def handle_select_reservation_for_change(reservation_id, userID, structured=False):
    reservation_ref = db.collection("Reservations").document(reservation_id)
    reservation_doc = reservation_ref.get()
    if not reservation_doc.exists:
        return https_fn.Response("변경할 예약을 찾을 수 없습니다.", status=404)

    reservation_data = reservation_doc.to_dict() or {}
    if str(reservation_data.get("userID") or "") != str(userID):
        return https_fn.Response("변경할 예약을 찾을 수 없습니다.", status=404)

    pending_ref = db.collection("PendingReservations").document(userID)
    pending_doc = pending_ref.get()
    pending_data = pending_doc.to_dict() if pending_doc.exists else {}
    requested_query = {
        "replaceReservationId": reservation_id,
        "ownerUid": pending_data.get("ownerUid", ""),
        "_structuredResponse": structured,
    }
    requested_mapping = {
        "requestedNewRoom": "newRoom",
        "requestedStartTime": "startTime",
        "requestedDuration": "duration",
        "requestedEventParticipants": "eventParticipants",
    }
    for pending_key, query_key in requested_mapping.items():
        value = pending_data.get(pending_key)
        if value not in (None, ""):
            requested_query[query_key] = value

    if any(key in requested_query for key in ("newRoom", "startTime", "duration", "eventParticipants")):
        return handle_change_reservation(requested_query, userID)

    start, end = reservation_time_range(reservation_data)
    if not start or not end:
        return https_fn.Response("예약 시간 정보를 확인할 수 없습니다.", status=400)

    duration = max(1, int((end - start).total_seconds() / 3600))
    target_pending = build_pending_reservation_data(
        room=reservation_data.get("roomID") or reservation_data.get("room"),
        start=start,
        duration=duration,
        event_participants=reservation_data.get("eventParticipants"),
        owner_uid=reservation_data.get("ownerUid", ""),
        event_name=reservation_data.get("eventName"),
        event_description=reservation_data.get("eventDescription", ""),
        event_target=reservation_data.get("eventTarget", ""),
        flow_type=FLOW_CHANGE_EXISTING_RESERVATION,
        replace_reservation_id=reservation_id,
    )
    target_pending["awaitingChangeDetails"] = True
    pending_ref.set(target_pending)

    room_id = target_pending.get("room")
    _, room_data = find_room(room_id)
    room_name = display_room_label(room_id, room_data)
    return https_fn.Response(
        f"{room_name} 예약을 선택했어요. "
        "변경할 인원, 시간 또는 강의실을 알려주세요.\n"
        "예: '3명으로 변경해줘'",
        status=200,
    )


def handle_change_reservation(query, userID):
    try:
        target_room_id, target_room_data = find_room(query.get("room"))
        target_reservation_room_id = (
            reservation_room_id(target_room_id, target_room_data)
            if target_room_id and target_room_data
            else None
        )
        new_room_id, new_room_data = find_room(query.get("newRoom"))
        new_reservation_room_id = (
            reservation_room_id(new_room_id, new_room_data)
            if new_room_id and new_room_data
            else None
        )
        logging.info(
            "[handle_change_reservation] target_room_id=%s, "
            "target_reservation_room_id=%s, userID=%s",
            target_room_id,
            target_reservation_room_id,
            userID,
        )

        target_start = None
        if query.get("targetStartTime"):
            try:
                target_start = datetime.fromisoformat(str(query.get("targetStartTime")))
                if target_start.tzinfo is None:
                    target_start = target_start.replace(tzinfo=KST)
            except (TypeError, ValueError):
                target_start = None

        replace_reservation_id = str(query.get("replaceReservationId") or "").strip()
        if replace_reservation_id:
            exact_doc = db.collection("Reservations").document(replace_reservation_id).get()
            exact_data = exact_doc.to_dict() if exact_doc.exists else None
            if exact_data and str(exact_data.get("userID") or "") == str(userID):
                res_id = replace_reservation_id
                res_data = exact_data
                start, end = reservation_time_range(res_data)
            else:
                res_id, res_data, start, end = None, None, None, None
        else:
            res_id, res_data, start, end = find_user_reservation(
                userID,
                room_id=target_reservation_room_id,
                target_start=target_start,
            )
        if not res_id:
            return https_fn.Response("변경할 예약이 없습니다.", status=404)

        new_duration = query.get("duration")
        new_participants = query.get("eventParticipants")
        new_start_time = query.get("startTime")
        duration_hours = int((end - start).total_seconds() / 3600) if end and start else 2

        if new_start_time:
            try:
                start = datetime.fromisoformat(new_start_time)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=KST)
            except:
                pass

        if new_duration:
            duration_hours = int(new_duration)

        if duration_hours < 1 or duration_hours > 6:
            return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

        end = start + timedelta(hours=duration_hours)
        now = datetime.now(KST)
        if start < now:
            return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)

        if has_conflict("userID", userID, start, end, exclude_id=res_id):
            return https_fn.Response("해당 시간에 이미 예약한 다른 강의실이 있어요.", status=409)
        final_room_id = new_reservation_room_id or res_data.get("roomID")
        if has_conflict("roomID", final_room_id, start, end, exclude_id=res_id):
            return https_fn.Response("해당 시간에 이미 강의실이 예약되어 있어요.", status=409)

        update_data = {
            "roomID": final_room_id,
            "startTime": format_korean_time(start),
            "endTime": format_korean_time(end),
            "startTimestamp": firestore.DELETE_FIELD,
            "endTimestamp": firestore.DELETE_FIELD,
        }

        if new_participants:
            participants_str = str(new_participants).strip()
            numeric_part = re.search(r'\d+', participants_str)
            if numeric_part:
                update_data["eventParticipants"] = int(numeric_part.group())

        db.collection("Reservations").document(res_id).update(update_data)
        
        _, room_data = find_room(final_room_id)
        room_name = display_room_label(final_room_id, room_data)
        
        return https_fn.Response(f"{room_name} 예약이 성공적으로 변경되었습니다 ✅", status=200)

    except Exception as e:
        logging.exception("[handle_change_reservation] 예외 발생")
        return https_fn.Response("예약 변경 중 오류가 발생했어요. 로그를 확인해주세요.", status=500)
