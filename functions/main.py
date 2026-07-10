from firebase_functions import https_fn, scheduler_fn
from firebase_admin import firestore, initialize_app, auth
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import re
import logging

from chat_history import delete_expired_chat_history, load_chat_history, save_chat_turn
from ai_response import ai_action, ai_card, make_ai_response
from ai_intents import (
    enrich_query_from_direct_parse,
    extract_recommendation_keywords,
    extract_room_ids,
    is_alternative_room_request,
    is_cancel_reservation_request,
    is_change_reservation_request,
    is_explicit_change_reservation_request,
    is_my_reservations_request,
    is_new_reservation_request,
    is_recommendation_or_lookup_request,
    is_reservation_confirmation,
    is_reservation_request_text,
    parse_duration_hours,
    parse_participant_count,
    recover_reserve_fields_from_text,
)
from room_service import (
    configure_room_service,
    display_room_label,
    find_available_rooms,
    find_room,
    handle_list_rooms,
    handle_list_rooms_by_building,
    handle_list_rooms_by_equipment,
    handle_query_equipment,
    handle_recommend_room,
    handle_room_availability,
)
from reservation_service import (
    FLOW_ALTERNATIVE_NEW_RESERVATION,
    FLOW_BLOCKED_EXISTING_RESERVATION,
    FLOW_CHANGE_EXISTING_RESERVATION,
    FLOW_NEW_RESERVATION,
    build_pending_reservation_data,
    build_reservation_document,
    can_confirm_pending,
    configure_reservation_service,
    find_conflicting_reservation,
    find_user_reservation,
    handle_cancel_reservation,
    handle_change_reservation,
    handle_change_reservation_selection,
    handle_confirm_reservation,
    handle_reserve,
    handle_select_reservation_for_change,
    has_conflict,
    infer_pending_flow_type,
    list_user_upcoming_reservations,
    missing_required_fields,
    normalize_event_participants,
    parse_participants_int,
    parse_reservation_start_and_duration,
    reservation_time_range,
    suggest_alternative_room_response,
)
from reservation_utils import (
    KST,
    extract_room_id,
    format_korean_time,
    parse_natural_korean_datetime,
    reservation_room_id,
)

# 환경 설정
load_dotenv()
initialize_app()


class _LazyFirestoreClient:
    """Create the Firestore client only when a function actually uses it.

    Firebase CLI imports this module during deployment discovery to read the
    function manifest. Creating firestore.client() at import time makes that
    discovery depend on local Application Default Credentials, so keep it lazy.
    """

    _client = None

    def _get_client(self):
        if self._client is None:
            self._client = firestore.client()
        return self._client

    def __getattr__(self, name):
        return getattr(self._get_client(), name)


db = _LazyFirestoreClient()
api_key = os.environ.get("GEMINI_API_KEY")
genai_client = genai.Client(api_key=api_key, vertexai=False)

configure_reservation_service(db, room_label_formatter=display_room_label)
configure_room_service(
    db,
    conflict_checker=has_conflict,
    reservation_time_range_fn=reservation_time_range,
    flow_new_reservation=FLOW_NEW_RESERVATION,
)


def handle_latest_notice(query, userID):
    docs = db.collection("Notices").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(1).get()
    if not docs:
        return https_fn.Response("공지사항이 없습니다.", status=200)
    notice = docs[0].to_dict()
    return https_fn.Response(f"[{notice['title']}]\n{notice['content']}", status=200)

def handle_my_reviews(query, userID):
    docs = db.collection("Reviews").where("userID", "==", userID).stream()
    reviews = [d.to_dict() for d in docs]
    if not reviews:
        return https_fn.Response("작성한 리뷰가 없습니다.", status=200)
    sorted_reviews = sorted(reviews, key=lambda x: x.get("createdAt", datetime.min), reverse=True)
    preview = sorted_reviews[:2]
    reply_lines = [f"{r.get('roomID', '?')}호: {r.get('comment', '')} (★{r.get('rating', '?')})" for r in preview]
    reply_lines.append("\n자세한 리뷰는 마이페이지에서 확인해 주세요 😊")
    return https_fn.Response("\n\n".join(reply_lines), status=200)

def handle_review_summary(query, userID):
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실을 찾을 수 없습니다.", status=404)
    room_name = room_data.get("name", room_id)
    docs = db.collection("Reviews").where("roomID", "==", room_id).stream()
    ratings, pos_comments, neg_comments = [], [], []
    for r in docs:
        review = r.to_dict()
        rating = review.get("rating")
        comment = review.get("comment", "")
        if rating is not None:
            ratings.append(rating)
            if rating >= 4:
                pos_comments.append(comment)
            elif rating <= 2:
                neg_comments.append(comment)
    if not ratings:
        return https_fn.Response(f"{room_name}에 등록된 후기가 없어요.", status=200)
    avg = round(sum(ratings) / len(ratings), 1)
    pos_ratio = round(len(pos_comments) / len(ratings) * 100)
    neg_ratio = 100 - pos_ratio
    pos_line = f'🟢 긍정 후기: "{pos_comments[-1]}"' if pos_comments else ""
    neg_line = f'🔴 부정 후기: "{neg_comments[-1]}"' if neg_comments else ""
    summary = f"""[{room_name} 강의실 평가 요약]
{pos_line}
{neg_line}
⭐ 평균 평점: {avg}점
📊 긍정 {pos_ratio}%, 부정 {neg_ratio}%"""
    return https_fn.Response(summary, status=200)

def handle_my_reservations(query, userID):
    reservations = list_user_upcoming_reservations(userID, limit=10)
    if not reservations:
        return https_fn.Response("현재 예약 및 예정된 예약이 없습니다.", status=200)

    lines = []
    for _, room_name, data in reservations[:10]:
        start_text = data.get("startTime", "?")
        end_text = data.get("endTime", "?")
        participants = data.get("eventParticipants")
        participant_text = f" / {participants}명" if participants else ""
        lines.append(f"- {room_name}: {start_text} ~ {end_text}{participant_text}")
    return https_fn.Response("현재 예약 및 예정된 예약:\n" + "\n".join(lines), status=200)

handlers = {
    "query_equipment": handle_query_equipment,
    "reserve": handle_reserve,
    "confirm_reservation": handle_confirm_reservation,
    "change_reservation": handle_change_reservation,
    "cancel_reservation": handle_cancel_reservation,
    "latest_notice": handle_latest_notice,
    "my_reviews": handle_my_reviews,
    "recommend_room": handle_recommend_room,
    "review_summary": handle_review_summary,
    "list_rooms": handle_list_rooms,
    "list_rooms_by_building": handle_list_rooms_by_building,
    "list_rooms_by_equipment": handle_list_rooms_by_equipment,
    "room_availability": handle_room_availability,
    "my_reservations": handle_my_reservations
}

FAQ_RULES = """
[강의실 이용 수칙 및 안내]
- 예약 가능 시간: 오전 9시부터 오후 10시까지 예약 가능합니다. (밤 10시 이후 예약 불가)
- 예약 단위: 최소 1시간부터 최대 6시간까지 예약 가능합니다.
- 취소 규정: 예약 시작 1시간 전까지 취소 가능하며, 노쇼(No-show) 시 1개월간 예약이 정지됩니다.
- 프로젝터 사용법: 프로젝터 리모컨은 각 강의실 앞 교탁 서랍에 비치되어 있습니다.
- 음식물 반입: 생수 외의 음료나 음식물 반입은 엄격히 금지됩니다.
- 최소 예약 인원: 최소 1명 이상이어야 예약이 가능합니다.
"""

@https_fn.on_request()
def ai_assistant(req: https_fn.Request) -> https_fn.Response:
    try:
        data = req.get_json(silent=True)
        if not isinstance(data, dict):
            return https_fn.Response("JSON 요청 본문이 필요합니다.", status=400)
        user_input = str(data.get("message", "")).strip()
        supports_structured_response = bool(data.get("supportsStructuredResponse"))
        if not user_input:
            return https_fn.Response("메시지를 입력해 주세요.", status=400)
        if len(user_input) > 2000:
            return https_fn.Response("메시지는 2,000자 이내로 입력해 주세요.", status=400)

        authorization = req.headers.get("Authorization", "")
        id_token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        uid = "unknown"
        if id_token:
            try:
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token.get("uid", "unknown")
            except Exception as e:
                logging.warning(f"Failed to verify token: {e}")
                return https_fn.Response("유효하지 않은 토큰입니다.", status=401)
        
        if uid == "unknown":
            logging.warning("UserID is unknown. Authentication is required.")
            return https_fn.Response("사용자 인증이 필요합니다. 다시 로그인해주세요.", status=401)

        # uid로 사용자 문서 조회하여 학번(studentId) 가져오기
        try:
            user_doc_ref = db.collection("User").document(uid)
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                raw_student_id = user_data.get("studentId")
                if not raw_student_id:
                    return https_fn.Response("사용자 정보에서 학번을 찾을 수 없습니다.", status=404)
                userID = str(raw_student_id)
            else:
                return https_fn.Response("사용자 정보를 찾을 수 없습니다.", status=404)
        except Exception:
            logging.exception("사용자 정보 조회 실패")
            return https_fn.Response("사용자 정보 조회 중 오류가 발생했습니다.", status=500)

        # ----------------------------------------------------
        # 1. Chat History 불러오기
        # ----------------------------------------------------
        history_ref, stored_messages, chat_history = load_chat_history(db, userID)

        now_kst = datetime.now(KST)

        def _store_direct_response(bot_text, status=200):
            save_chat_turn(history_ref, stored_messages, user_input, bot_text)
            return https_fn.Response(bot_text, status=status)

        pending_ref = db.collection("PendingReservations").document(userID)
        pending_doc_for_guard = pending_ref.get()
        pending_data_for_guard = pending_doc_for_guard.to_dict() if pending_doc_for_guard.exists else {}

        change_selection_prefix = "예약 변경 대상 선택::"
        if user_input.startswith(change_selection_prefix):
            selected_reservation_id = user_input[len(change_selection_prefix):].strip()
            res = handle_select_reservation_for_change(
                selected_reservation_id,
                userID,
                structured=supports_structured_response,
            )
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        pending_start_for_guard = None
        pending_start_raw = pending_data_for_guard.get("startTime")
        if pending_start_raw:
            try:
                pending_start_for_guard = datetime.fromisoformat(str(pending_start_raw))
                if pending_start_for_guard.tzinfo is None:
                    pending_start_for_guard = pending_start_for_guard.replace(tzinfo=KST)
            except (TypeError, ValueError):
                pending_start_for_guard = None

        preliminary_room_id = extract_room_id(user_input)
        preliminary_change_request = is_change_reservation_request(user_input)
        preliminary_cancel_request = is_cancel_reservation_request(user_input)
        default_date_for_direct_parse = pending_start_for_guard
        if not default_date_for_direct_parse and (preliminary_change_request or preliminary_cancel_request):
            try:
                _, _, existing_start_for_guard, _ = find_user_reservation(
                    userID,
                    room_id=preliminary_room_id,
                )
                if existing_start_for_guard:
                    default_date_for_direct_parse = existing_start_for_guard
            except Exception as e:
                logging.warning("[ai_assistant] Existing reservation date lookup failed: %s", e)

        direct_start = parse_natural_korean_datetime(
            user_input,
            now_kst,
            default_date=default_date_for_direct_parse,
        )
        direct_room_id = extract_room_id(user_input)
        direct_room_ids = extract_room_ids(user_input)
        direct_participants = parse_participant_count(user_input)
        direct_duration = parse_duration_hours(user_input)
        wants_alternative_room = is_alternative_room_request(user_input)
        wants_new_reservation = is_new_reservation_request(user_input)
        wants_cancel_reservation = preliminary_cancel_request
        wants_change_reservation = preliminary_change_request
        explicitly_changes_existing_reservation = is_explicit_change_reservation_request(user_input)
        wants_my_reservations = is_my_reservations_request(user_input)
        confirms_pending = (
            pending_doc_for_guard.exists
            and not wants_new_reservation
            and is_reservation_confirmation(user_input)
        )

        if wants_new_reservation and not any([direct_start, direct_room_id, direct_participants]):
            pending_ref.delete()
            return _store_direct_response(
                "\uc88b\uc544\uc694. \uc0c8 \uc608\uc57d\uc73c\ub85c \uc2dc\uc791\ud560\uac8c\uc694. "
                "\uc6d0\ud558\ub294 \ub0a0\uc9dc, \uc2dc\uac04, \uac15\uc758\uc2e4, \uc778\uc6d0\uc744 \uc54c\ub824\uc8fc\uc138\uc694.\n"
                "\uc608: \ubaa8\ub808 \uc624\uc804 11\uc2dc\uc5d0 7202 \uac15\uc758\uc2e4 5\uba85",
                status=200,
            )

        if confirms_pending:
            res = handle_confirm_reservation(
                {"ownerUid": uid, "_structuredResponse": supports_structured_response},
                userID,
            )
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_cancel_reservation:
            direct_query = {"ownerUid": uid}
            if direct_room_id:
                direct_query["room"] = direct_room_id
            if direct_start:
                direct_query["startTime"] = direct_start.isoformat()
            res = handle_cancel_reservation(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_my_reservations:
            res = handle_my_reservations({"ownerUid": uid}, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_alternative_room and explicitly_changes_existing_reservation:
            res_id, res_data, existing_start, existing_end = find_user_reservation(
                userID,
                room_id=direct_room_id,
                target_start=direct_start,
            )
            if not res_id or not res_data or not existing_start or not existing_end:
                return _store_direct_response("변경할 예약이 없습니다.", status=404)

            existing_room_id = str(res_data.get("roomID") or res_data.get("room") or "").strip()
            _, existing_room_data = find_room(existing_room_id)
            existing_room_name = display_room_label(existing_room_id, existing_room_data)
            duration_hours = max(1, int((existing_end - existing_start).total_seconds() / 3600))
            participants = res_data.get("eventParticipants") or direct_participants or 1

            res = suggest_alternative_room_response(
                existing_room_name,
                existing_start,
                existing_end,
                duration_hours,
                participants,
                uid,
                userID,
                exclude_room_ids={existing_room_id},
                replace_reservation_id=res_id,
                structured=supports_structured_response,
            )
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if wants_change_reservation and not wants_alternative_room:
            direct_query = {
                "ownerUid": uid,
                "_structuredResponse": supports_structured_response,
            }
            pending_replace_reservation_id = (
                pending_data_for_guard.get("replaceReservationId")
                if pending_data_for_guard.get("flowType") == FLOW_CHANGE_EXISTING_RESERVATION
                else None
            )
            if pending_replace_reservation_id:
                direct_query["replaceReservationId"] = pending_replace_reservation_id
            if len(direct_room_ids) >= 2:
                direct_query["room"] = direct_room_ids[0]
                direct_query["newRoom"] = direct_room_ids[1]
            elif len(direct_room_ids) == 1:
                if direct_start or direct_participants is not None or direct_duration is not None:
                    direct_query["room"] = direct_room_ids[0]
                else:
                    direct_query["newRoom"] = direct_room_ids[0]
            if direct_start:
                direct_query["startTime"] = direct_start.isoformat()
            if pending_start_for_guard:
                direct_query["targetStartTime"] = pending_start_for_guard.isoformat()
            if direct_participants is not None:
                direct_query["eventParticipants"] = str(direct_participants)
            if direct_duration is not None:
                direct_query["duration"] = direct_duration
            has_change_details = any(
                key in direct_query for key in ("newRoom", "startTime", "eventParticipants", "duration")
            )
            has_change_target = bool(direct_query.get("room") or direct_query.get("replaceReservationId"))
            if not has_change_target:
                res = handle_change_reservation_selection(direct_query, userID)
                bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
                return _store_direct_response(bot_text, getattr(res, "status_code", 200))
            if not has_change_details:
                return _store_direct_response(
                    "\ubcc0\uacbd\ud560 \uc778\uc6d0, \uc2dc\uac04 \ub610\ub294 \uac15\uc758\uc2e4\uc744 \uc54c\ub824\uc8fc\uc138\uc694. "
                    "\uc608: '3\uba85\uc73c\ub85c \ubcc0\uacbd\ud574\uc918'",
                    status=400,
                )
            res = handle_change_reservation(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        if (
            is_recommendation_or_lookup_request(user_input)
            and not wants_new_reservation
            and not wants_change_reservation
            and not wants_cancel_reservation
            and not direct_room_id
        ):
            recommendation_query = {
                "ownerUid": uid,
                "keywords": extract_recommendation_keywords(user_input),
                "_structuredResponse": supports_structured_response,
            }
            if direct_start:
                recommendation_query["afterTime"] = direct_start.isoformat()
                recommendation_query["startTime"] = direct_start.isoformat()
            if direct_duration is not None:
                recommendation_query["duration"] = direct_duration
            if direct_participants is not None:
                recommendation_query["eventParticipants"] = str(direct_participants)
            res = handle_recommend_room(recommendation_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        should_handle_reservation_directly = (
            wants_alternative_room
            or (
                pending_doc_for_guard.exists
                and direct_participants is not None
                and is_reservation_request_text(user_input)
            )
            or (is_reservation_request_text(user_input) and (direct_start or direct_room_id))
            or (direct_start and direct_room_id)
            or (wants_new_reservation and (direct_start or direct_room_id or direct_participants is not None))
        )
        if should_handle_reservation_directly:
            if wants_new_reservation:
                pending_ref.delete()
            direct_query = {
                "ownerUid": uid,
                "needsConfirmation": True,
                "rawUserInput": user_input,
                "_structuredResponse": supports_structured_response,
            }
            enrich_query_from_direct_parse(
                direct_query,
                room_id=direct_room_id,
                start=direct_start,
                participants=direct_participants,
                duration=direct_duration,
            )
            if wants_alternative_room:
                direct_query["allowAlternativeRoom"] = True
                if explicitly_changes_existing_reservation:
                    direct_query["explicitChangeReservation"] = True
                direct_query.pop("room", None)

            res = handle_reserve(direct_query, userID)
            bot_text = res.data.decode("utf-8") if hasattr(res, "data") else str(res)
            return _store_direct_response(bot_text, getattr(res, "status_code", 200))

        # ----------------------------------------------------
        # 2. Function Calling 도구(Tools) 정의
        # ----------------------------------------------------
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(name="query_equipment", description="특정 강의실의 특정 기자재 유무 확인", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "item": types.Schema(type="STRING")}, required=["room", "item"])),
                    types.FunctionDeclaration(name="reserve", description="강의실 예약 제안 또는 확정. 첫 예약 요청은 서버가 확인 메시지로 돌려주며, 사용자가 명시적으로 확정하면 confirmed=true로 호출하세요. 사용자가 빈 강의실을 알아서 예약해달라고 하면 room 파라미터를 생략할 수 있습니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING", description="강의실 이름. 빈 강의실 알아서 예약시 생략가능"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER"), "confirmed": types.Schema(type="BOOLEAN")}, required=["startTime", "eventParticipants"])),
                    types.FunctionDeclaration(name="confirm_reservation", description="사용자가 직전에 제안된 pending 예약을 '예약 확정', '네', '그걸로' 등으로 승인했을 때 호출", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="cancel_reservation", description="예약 취소. 강의실이나 시간이 없으면 사용자의 가장 가까운 예정 예약을 취소합니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING")})),
                    types.FunctionDeclaration(name="change_reservation", description="예약 변경. room은 변경 대상 기존 예약의 강의실, newRoom은 새 강의실입니다. 시간/인원만 바꾸는 경우 newRoom은 생략합니다.", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING"), "newRoom": types.Schema(type="STRING"), "targetStartTime": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")})),
                    types.FunctionDeclaration(name="latest_notice", description="최신 공지 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="my_reviews", description="내가 쓴 리뷰 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="recommend_room", description="Recommend or search available lecture rooms. If the user mentioned a reservation time, pass it as ISO 8601 in afterTime or startTime. Also pass duration and eventParticipants when available.", parameters=types.Schema(type="OBJECT", properties={"keywords": types.Schema(type="ARRAY", items=types.Schema(type="STRING")), "afterTime": types.Schema(type="STRING"), "startTime": types.Schema(type="STRING"), "duration": types.Schema(type="INTEGER"), "eventParticipants": types.Schema(type="INTEGER")})),
                    types.FunctionDeclaration(name="review_summary", description="특정 강의실 리뷰 요약", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING")}, required=["room"])),
                    types.FunctionDeclaration(name="list_rooms", description="전체 강의실 조회", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="list_rooms_by_building", description="특정 건물 강의실 조회 (예: 5강의동)", parameters=types.Schema(type="OBJECT", properties={"building": types.Schema(type="STRING")}, required=["building"])),
                    types.FunctionDeclaration(name="list_rooms_by_equipment", description="특정 기자재 있는 강의실 조회", parameters=types.Schema(type="OBJECT", properties={"item": types.Schema(type="STRING")}, required=["item"])),
                    types.FunctionDeclaration(name="room_availability", description="특정 강의실의 오늘 예약 내역 확인", parameters=types.Schema(type="OBJECT", properties={"room": types.Schema(type="STRING")}, required=["room"])),
                    types.FunctionDeclaration(name="my_reservations", description="내 예약 내역 확인", parameters=types.Schema(type="OBJECT", properties={})),
                    types.FunctionDeclaration(name="get_facility_rules", description="강의실 이용 수칙, 취소 규정, 기자재 사용법 등을 조회", parameters=types.Schema(type="OBJECT", properties={"query": types.Schema(type="STRING")}, required=["query"])),
                ]
            )
        ]

        now_kst = datetime.now(KST)
        system_prompt = f"""당신은 PickDream의 강의실 예약 및 안내를 돕는 AI 비서입니다.
항상 존댓말을 사용하고 이모지(😊)를 적절히 사용해 친절하게 응답하세요.

오늘 날짜와 현재 시간은 {now_kst.strftime('%Y-%m-%d %H:%M:%S KST')}입니다.
이를 기준으로 '내일', '모레', '오후 2시' 등의 시간을 정확한 ISO 8601 형식(예: 2025-03-15T14:00:00)으로 변환해 도구 파라미터로 넘기세요.

**중요 지침:**
- 단순 대화는 텍스트로 자연스럽게 답변하세요.
- 예약, 검색, 정보 조회가 필요하면 반드시 적절한 도구(Function)를 호출하세요.
- 예약을 확정(reserve)하려면 '시작 시간', '인원수'가 반드시 필요합니다.
- 첫 예약 요청에서는 예약 내용을 먼저 확인받아야 합니다. 서버가 확인 메시지를 반환하면 사용자에게 그대로 안내하세요.
- 사용자가 "예약 확정", "네", "그걸로", "진행해"처럼 방금 제안된 예약을 명시적으로 승인하면 confirm_reservation 도구를 호출하세요.
- 사용자가 "알아서 예약해줘", "빈 방 예약해줘" 등 강의실 이름을 명시하지 않고 예약을 원하면 직접 되묻지 말고, **'reserve' 도구의 'room' 파라미터를 생략**하여 서버가 빈 강의실을 찾아 예약 내용을 먼저 제안하도록 하세요.
- 특정 학교명, 기관명, AI 비서 이름은 사용자가 직접 말하지 않는 한 임의로 언급하지 마세요.
- 절대 임의의 강의실이나 시간을 지어내지 마세요.
"""

        # ----------------------------------------------------
        # 3. LLM 호출
        # ----------------------------------------------------
        contents = chat_history + [{"role": "user", "parts": [{"text": user_input}]}]

        try:
            response = genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools,
                    temperature=0.1
                )
            )
        except Exception:
            logging.exception("Gemini 호출 실패")
            return https_fn.Response("AI 서버가 혼잡하여 요청을 처리할 수 없어요. 잠시 후 다시 시도해 주세요.", status=503)

        bot_text = ""
        is_history_clear = False

        # ----------------------------------------------------
        # 4. 도구 호출(Function Calls) 처리
        # ----------------------------------------------------
        if response.function_calls:
            fc = response.function_calls[0]
            action = fc.name
            logging.info(f"[Function Call] {action} args: {fc.args}")
            
            if action == "get_facility_rules":
                bot_text = f"알려드릴게요! 🧐\n\n{FAQ_RULES}\n\n도움이 더 필요하신가요? 😊"
            else:
                query = {
                    "action": action,
                    "rawUserInput": user_input,
                    "_structuredResponse": supports_structured_response,
                }
                for k, v in fc.args.items():
                    query[k] = v
                query["ownerUid"] = uid
                if action in {"reserve", "recommend_room"} and is_alternative_room_request(user_input):
                    query["allowAlternativeRoom"] = True
                    if is_explicit_change_reservation_request(user_input):
                        query["explicitChangeReservation"] = True
                    query.pop("room", None)
                
                if "room" in query and query["room"]:
                    room_id, _ = find_room(query["room"])
                    if room_id:
                        query["room"] = room_id
                if "newRoom" in query and query["newRoom"]:
                    new_room_id, _ = find_room(query["newRoom"])
                    if new_room_id:
                        query["newRoom"] = new_room_id

                pending_start_for_date = None
                if action in {"reserve", "change_reservation", "recommend_room", "cancel_reservation"}:
                    try:
                        pending_doc = db.collection("PendingReservations").document(userID).get()
                        if pending_doc.exists:
                            pending_start_raw = (pending_doc.to_dict() or {}).get("startTime")
                            if pending_start_raw:
                                pending_start_for_date = datetime.fromisoformat(str(pending_start_raw))
                                if pending_start_for_date.tzinfo is None:
                                    pending_start_for_date = pending_start_for_date.replace(tzinfo=KST)
                    except Exception as e:
                        logging.warning("[ai_assistant] Pending start date lookup failed: %s", e)

                inferred_start = parse_natural_korean_datetime(
                    user_input,
                    now_kst,
                    default_date=pending_start_for_date,
                )
                if inferred_start and action in {"reserve", "change_reservation", "recommend_room"}:
                    inferred_start_iso = inferred_start.isoformat()
                    if action == "recommend_room":
                        # Guardrail: recommend_room used to default to now+10min when the
                        # model omitted time. Preserve the user's explicit Korean time.
                        query["afterTime"] = inferred_start_iso
                        query["startTime"] = inferred_start_iso
                    else:
                        query["startTime"] = inferred_start_iso
                elif inferred_start and action == "cancel_reservation":
                    query["startTime"] = inferred_start.isoformat()

                if action == "reserve":
                    enrich_query_from_direct_parse(
                        query,
                        room_id=direct_room_id,
                        start=inferred_start or direct_start,
                        participants=direct_participants,
                        duration=direct_duration,
                    )
                elif action == "change_reservation":
                    enrich_query_from_direct_parse(
                        query,
                        start=inferred_start or direct_start,
                        participants=direct_participants,
                        duration=direct_duration,
                    )

                if action == "recommend_room":
                    query["keywords"] = list(query.get("keywords", []))
                    if query.get("eventParticipants"):
                        query["eventParticipants"] = str(query["eventParticipants"])
                    if query.get("duration"):
                        query["duration"] = int(query["duration"])
                elif action in ["reserve", "change_reservation"]:
                    if query.get("eventParticipants"):
                        query["eventParticipants"] = str(query["eventParticipants"])
                    if query.get("duration"):
                        query["duration"] = int(query["duration"])
                    if action == "reserve" and not query.get("confirmed") and not is_reservation_confirmation(user_input):
                        query["needsConfirmation"] = True
                        
                if action in handlers:
                    res = handlers[action](query, userID)
                    bot_text = res.data.decode('utf-8') if hasattr(res, 'data') else str(res)
                    
                    if action == "reserve" and "예약되었습니다" in bot_text:
                        is_history_clear = True
                    elif action == "cancel_reservation" and "취소되었습니다" in bot_text:
                        is_history_clear = True
                else:
                    bot_text = "지원하지 않는 기능을 호출했어요."
        else:
            bot_text = (response.text or "응답을 생성하지 못했어요. 다시 시도해 주세요.").strip()

        # ----------------------------------------------------
        # 5. Chat History 업데이트
        # ----------------------------------------------------
        if is_history_clear:
            history_ref.delete()
        else:
            save_chat_turn(history_ref, stored_messages, user_input, bot_text)

        return https_fn.Response(bot_text, status=200)

    except Exception:
        logging.exception("예외 발생:")
        return https_fn.Response("알 수 없는 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)


@scheduler_fn.on_schedule(schedule="0 4 * * *", timezone="Asia/Seoul")
def cleanup_old_chat_history(event: scheduler_fn.ScheduledEvent) -> None:
    deleted = delete_expired_chat_history(db)
    logging.info("Deleted %s expired ChatHistory documents.", deleted)
