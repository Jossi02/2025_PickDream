"""Reservation change workflows.

The compatibility façade in reservation_service.py injects Firestore and lookup
dependencies, preserving existing callers and test seams.
"""

import logging
import re
from datetime import datetime, timedelta

from firebase_admin import firestore
from firebase_functions import https_fn

from ai_response import ai_action, ai_card, make_ai_response
from reservation_domain import (
    FLOW_CHANGE_EXISTING_RESERVATION,
    build_pending_reservation_data,
    reservation_time_range,
)
from reservation_utils import KST, format_korean_time, reservation_room_id


def execute_change_reservation_selection(
    query,
    userID,
    *,
    db,
    list_user_upcoming_reservations,
):
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


def execute_select_reservation_for_change(
    reservation_id,
    userID,
    structured=False,
    *,
    db,
    handle_change_reservation,
    find_room,
    display_room_label,
):
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


def execute_change_reservation(
    query,
    userID,
    *,
    db,
    find_room,
    find_user_reservation,
    has_conflict,
    display_room_label,
):
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
        existing_room_id = str(res_data.get("roomID") or res_data.get("room") or "").strip()
        resolved_existing_room_id, _ = find_room(existing_room_id)
        final_room_id = new_reservation_room_id or resolved_existing_room_id
        if not final_room_id:
            return https_fn.Response("예약 강의실 정보를 확인할 수 없습니다.", status=400)
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
