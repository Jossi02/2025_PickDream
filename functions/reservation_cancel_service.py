"""Cancellation workflow for reservations."""

import logging
from datetime import datetime

from firebase_functions import https_fn

from reservation_utils import KST, reservation_room_id


def handle_cancel_reservation(
    query,
    user_id,
    *,
    db,
    find_room,
    find_user_reservation,
    list_user_upcoming_reservations,
    display_room_label,
):
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
            user_id,
        )

        if not target_reservation_room_id and not target_start and not query.get("forceClosest"):
            candidates = list_user_upcoming_reservations(user_id, limit=5)
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

        reservation_id, reservation_data, _, _ = find_user_reservation(
            user_id,
            room_id=target_reservation_room_id,
            target_start=target_start,
        )
        if not reservation_id:
            return https_fn.Response("취소할 예약이 없습니다.", status=404)

        cancelled_room_id = reservation_data.get("roomID")
        _, cancelled_room_data = find_room(cancelled_room_id)
        cancelled_room_name = display_room_label(cancelled_room_id, cancelled_room_data)
        db.collection("Reservations").document(reservation_id).delete()

        return https_fn.Response(
            f"{cancelled_room_name} 예약이 취소되었습니다 ✅",
            status=200,
        )
    except Exception:
        logging.exception("[handle_cancel_reservation] 예외 발생")
        return https_fn.Response(
            "예약 취소 중 오류가 발생했어요. 로그를 확인해주세요.",
            status=500,
        )

