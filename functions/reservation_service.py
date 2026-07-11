import logging
import re
from datetime import datetime, timedelta

from firebase_admin import firestore
from firebase_functions import https_fn

from ai_intents import recover_reserve_fields_from_text
from ai_response import ai_action, ai_card, make_ai_response
from room_service import display_room_label, find_available_rooms, find_room
from reservation_cancel_service import handle_cancel_reservation as execute_cancel_reservation
from reservation_change_service import (
    execute_change_reservation,
    execute_change_reservation_selection,
    execute_select_reservation_for_change,
)
from reservation_domain import (
    FLOW_ALTERNATIVE_NEW_RESERVATION,
    FLOW_BLOCKED_EXISTING_RESERVATION,
    FLOW_CHANGE_EXISTING_RESERVATION,
    FLOW_NEW_RESERVATION,
    build_pending_reservation_data,
    build_reservation_document,
    can_confirm_pending,
    infer_pending_flow_type,
    missing_required_fields,
    normalize_event_participants,
    parse_participants_int,
    parse_reservation_start_and_duration,
    reservation_time_range,
)
from reservation_repository import (
    find_conflicting_reservation as repository_find_conflicting_reservation,
    find_user_reservation as repository_find_user_reservation,
    has_conflict as repository_has_conflict,
    list_user_upcoming_reservations as repository_list_user_upcoming_reservations,
    reservation_documents_for_field as repository_reservation_documents_for_field,
)

from reservation_utils import (
    KST,
    format_korean_time,
    reservation_room_id,
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
    yield from repository_reservation_documents_for_field(_require_db(), field, value)


def has_conflict(field: str, value: str, start, end, exclude_id: str = None):
    return repository_has_conflict(
        _reservation_documents_for_field,
        field,
        value,
        start,
        end,
        exclude_id=exclude_id,
    )


def find_conflicting_reservation(field: str, value: str, start, end, exclude_id: str = None):
    return repository_find_conflicting_reservation(
        _reservation_documents_for_field,
        field,
        value,
        start,
        end,
        exclude_id=exclude_id,
    )


def find_user_reservation(userID, room_id=None, target_start=None):
    return repository_find_user_reservation(
        _require_db(),
        userID,
        room_id=room_id,
        target_start=target_start,
    )


def list_user_upcoming_reservations(userID, limit=3):
    return repository_list_user_upcoming_reservations(
        _require_db(),
        userID,
        room_label_formatter=_format_room_label,
        limit=limit,
    )
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
    return execute_cancel_reservation(
        query,
        userID,
        db=_require_db(),
        find_room=find_room,
        find_user_reservation=find_user_reservation,
        list_user_upcoming_reservations=list_user_upcoming_reservations,
        display_room_label=display_room_label,
    )
def handle_change_reservation_selection(query, userID):
    return execute_change_reservation_selection(
        query,
        userID,
        db=_require_db(),
        list_user_upcoming_reservations=list_user_upcoming_reservations,
    )


def handle_select_reservation_for_change(reservation_id, userID, structured=False):
    return execute_select_reservation_for_change(
        reservation_id,
        userID,
        structured,
        db=_require_db(),
        handle_change_reservation=handle_change_reservation,
        find_room=find_room,
        display_room_label=display_room_label,
    )


def handle_change_reservation(query, userID):
    return execute_change_reservation(
        query,
        userID,
        db=_require_db(),
        find_room=find_room,
        find_user_reservation=find_user_reservation,
        has_conflict=has_conflict,
        display_room_label=display_room_label,
    )
