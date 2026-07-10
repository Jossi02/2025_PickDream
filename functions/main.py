from firebase_functions import https_fn, scheduler_fn
from firebase_admin import firestore, initialize_app, auth
from google import genai
from dotenv import load_dotenv
from datetime import datetime
import os
import logging

from ai_orchestrator import process_ai_message
from chat_history import delete_expired_chat_history
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

        return process_ai_message(
            db=db,
            genai_client=genai_client,
            handlers=handlers,
            faq_rules=FAQ_RULES,
            user_input=user_input,
            user_id=userID,
            uid=uid,
            supports_structured_response=supports_structured_response,
        )
    except Exception:
        logging.exception("예외 발생:")
        return https_fn.Response("알 수 없는 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", status=500)


@scheduler_fn.on_schedule(schedule="0 4 * * *", timezone="Asia/Seoul")
def cleanup_old_chat_history(event: scheduler_fn.ScheduledEvent) -> None:
    deleted = delete_expired_chat_history(db)
    logging.info("Deleted %s expired ChatHistory documents.", deleted)
