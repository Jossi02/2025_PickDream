from datetime import datetime, timedelta
import re

from firebase_functions import https_fn

from reservation_utils import (
    KST,
    coerce_capacity,
    extract_room_id,
    reservation_room_id,
    room_id_aliases,
)


_db = None
_has_conflict = None
_reservation_time_range = None
_flow_new_reservation = "new_reservation"


def configure_room_service(
    db_client,
    conflict_checker=None,
    reservation_time_range_fn=None,
    flow_new_reservation=None,
):
    global _db, _has_conflict, _reservation_time_range, _flow_new_reservation
    _db = db_client
    _has_conflict = conflict_checker
    _reservation_time_range = reservation_time_range_fn
    if flow_new_reservation:
        _flow_new_reservation = flow_new_reservation


def _require_db():
    if _db is None:
        raise RuntimeError("room_service is not configured with a Firestore client")
    return _db


def _require_conflict_checker():
    if _has_conflict is None:
        raise RuntimeError("room_service is not configured with a conflict checker")
    return _has_conflict


def _require_reservation_time_range():
    if _reservation_time_range is None:
        raise RuntimeError("room_service is not configured with reservation_time_range")
    return _reservation_time_range


def find_room(room_identifier):
    if not room_identifier:
        return None, None

    db = _require_db()
    room_identifier = str(room_identifier).strip()

    doc = db.collection("rooms").document(room_identifier).get()
    if doc.exists:
        return doc.id, doc.to_dict()

    docs = db.collection("rooms").where("name", "==", room_identifier).get()
    if docs:
        return docs[0].id, docs[0].to_dict()

    room_num = extract_room_id(room_identifier)
    if room_num:
        all_rooms = db.collection("rooms").stream()
        for r_doc in all_rooms:
            r_data = r_doc.to_dict()
            if reservation_room_id(r_doc.id, r_data) == room_num:
                return r_doc.id, r_data

    all_rooms = db.collection("rooms").stream()
    for r_doc in all_rooms:
        r_data = r_doc.to_dict()
        name = r_data.get("name", "")
        if room_identifier in name or name in room_identifier:
            return r_doc.id, r_data

    return None, None


def display_room_label(room_id, room_data=None):
    canonical_id = None
    if room_data:
        canonical_id = reservation_room_id(str(room_id or ""), room_data)
    canonical_id = canonical_id or extract_room_id(room_id) or str(room_id or "").strip()
    if canonical_id:
        return f"{canonical_id} 강의실"
    if room_data and room_data.get("name"):
        return room_data.get("name")
    return "강의실"


def find_available_rooms(start, end, person_count=0, exclude_room_ids=None):
    db = _require_db()
    has_conflict = _require_conflict_checker()
    exclude_room_ids = {
        alias
        for room_id in (exclude_room_ids or [])
        for alias in room_id_aliases(room_id)
    }
    matched = []
    for doc in db.collection("rooms").stream():
        r_data = doc.to_dict()
        canonical_room_id = reservation_room_id(doc.id, r_data)
        if any(alias in exclude_room_ids for alias in room_id_aliases(canonical_room_id)):
            continue

        cap = coerce_capacity(r_data.get("capacity"))
        if person_count > 0 and cap < person_count:
            continue

        if not has_conflict("roomID", canonical_room_id, start, end):
            matched.append((cap, canonical_room_id, doc.id, r_data))

    matched.sort()
    return matched


def handle_query_equipment(query, userID):
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실이 존재하지 않습니다.", status=404)
    eq = room_data.get("equipment", [])
    item = query.get("item")
    room_name = room_data.get("name", room_id)
    if not item or item in ["뭐", "무엇", "있는지", "있는가"]:
        eq_list = ", ".join(eq) if eq else "없음"
        return https_fn.Response(f"{room_name}에 있는 기자재: {eq_list}", status=200)
    return https_fn.Response(f"{room_name}에 '{item}'이(가) {'있습니다' if item in eq else '없습니다' }.", status=200)


def handle_recommend_room(query, userID):
    db = _require_db()
    has_conflict = _require_conflict_checker()
    keywords = query.get("keywords", [])
    now = datetime.now(KST)
    try:
        duration = int(query.get("duration") or 2)
    except (TypeError, ValueError):
        return https_fn.Response("이용 시간은 숫자로 입력해 주세요.", status=400)
    if duration < 1 or duration > 6:
        return https_fn.Response("예약 시간은 최소 1시간, 최대 6시간까지만 가능합니다.", status=400)

    person_count = next(
        (int(k.replace("명", "")) for k in keywords if k.endswith("명") and k[:-1].isdigit()),
        None,
    )
    if person_count is None and query.get("eventParticipants"):
        try:
            num = re.search(r"\d+", str(query.get("eventParticipants")))
            if num:
                person_count = int(num.group())
        except Exception:
            pass

    require_available_now = "지금" in keywords
    after_time_str = query.get("afterTime") or query.get("startTime")
    base_time = now

    if after_time_str:
        try:
            base_time = datetime.fromisoformat(after_time_str)
            if base_time.tzinfo is None:
                base_time = base_time.replace(tzinfo=KST)
            require_available_now = True
        except (TypeError, ValueError):
            return https_fn.Response("조회 시간이 올바른 형식이 아니에요.", status=400)

    base_time = base_time.astimezone(KST)
    if after_time_str and base_time <= now:
        return https_fn.Response("예약 시작 시간은 현재 시간 이후여야 해요.", status=400)
    end_time = base_time + timedelta(hours=duration)

    matched = []

    for doc in db.collection("rooms").stream():
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        eq = data.get("equipment", [])
        cap = coerce_capacity(data.get("capacity"))

        if person_count is not None and cap < person_count:
            continue

        if require_available_now:
            if has_conflict("roomID", room_id, base_time, end_time):
                continue

        score = sum(1 for k in keywords if k in eq)

        if score > 0 or person_count is not None or require_available_now:
            matched.append((-score, cap, room_id, data))

    if not matched:
        return https_fn.Response("조건에 맞는 강의실이 없어요 😥", status=200)

    matched.sort(key=lambda item: item[:3])
    _, _, room_id, best = matched[0]

    location = best.get("location") or best.get("buildingName") or "정보 없음"
    capacity = best.get("capacity", "정보 없음")
    equipment = ", ".join(best.get("equipment", [])) or "없음"

    reviews = db.collection("Reviews").where("roomID", "==", room_id).stream()
    ratings, pos_comments, neg_comments, latest_comment, latest_time = [], [], [], None, None
    for r in reviews:
        review = r.to_dict()
        rating = review.get("rating")
        comment = review.get("comment", "")
        created = review.get("createdAt")
        if rating is not None:
            ratings.append(rating)
            if rating >= 4:
                pos_comments.append(comment)
            elif rating <= 2:
                neg_comments.append(comment)
        if created and comment and (not latest_time or str(created) > str(latest_time)):
            latest_comment, latest_time = comment, created

    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    pos_rate = round(len(pos_comments) / len(ratings) * 100) if ratings else 0
    neg_rate = 100 - pos_rate if ratings else 0

    response = f"""조건에 맞는 강의실을 찾아봤어요! 😊
📍 위치: {location}
🏫 강의실: {display_room_label(room_id, best)} (최대 {capacity}명)
🛠️ 기자재: {equipment}"""
    if latest_comment:
        response += f'\n📝 최근 후기: "{latest_comment}"'
    if avg is not None:
        response += f"\n⭐ 평균 평점: {avg}점\n📊 긍정 {pos_rate}%, 부정 {neg_rate}%"

    if after_time_str:
        response += "\n\n이 강의실로 예약하려면 '예약해줘'처럼 다시 말씀해 주세요."

    if query.get("createPending"):
        if after_time_str:
            pending_start_time = base_time.astimezone(KST).isoformat()
        else:
            pending_start_time = (base_time + timedelta(minutes=10)).astimezone(KST).isoformat()

        pending_data = {
            "room": room_id,
            "startTime": pending_start_time,
            "duration": duration,
            "flowType": _flow_new_reservation,
            "eventName": query.get("eventName", "추천 예약"),
        }
        if person_count is not None:
            pending_data["eventParticipants"] = f"{person_count}명"

        db.collection("PendingReservations").document(userID).set(pending_data, merge=True)

    return https_fn.Response(response, status=200)


def handle_list_rooms(query, userID):
    db = _require_db()
    docs = db.collection("rooms").stream()
    rooms = [doc.id for doc in docs]
    return https_fn.Response("전체 강의실: " + ", ".join(rooms), status=200)


def handle_list_rooms_by_building(query, userID):
    db = _require_db()
    target = query.get("building")
    if not target:
        return https_fn.Response("건물명을 입력해 주세요. 예: '5강의동'", status=400)
    docs = db.collection("rooms").where("buildingDetail", "==", target).stream()
    room_ids = [doc.id for doc in docs]
    if not room_ids:
        return https_fn.Response(f"'{target}'에 해당하는 강의실이 없어요.", status=200)
    return https_fn.Response(f"{target}의 강의실 목록: {', '.join(room_ids)}", status=200)


def handle_list_rooms_by_equipment(query, userID):
    db = _require_db()
    item = query.get("item")
    if not item:
        return https_fn.Response("기자재를 입력해 주세요. 예: '마이크'", status=400)
    docs = db.collection("rooms").where("equipment", "array_contains", item).stream()
    room_names = []
    for doc in docs:
        data = doc.to_dict()
        room_id = reservation_room_id(doc.id, data)
        room_names.append(display_room_label(room_id, data))
    if not room_names:
        return https_fn.Response(f"'{item}'이(가) 있는 강의실이 없어요.", status=200)
    return https_fn.Response(f"'{item}'이(가) 있는 강의실: {', '.join(room_names)}", status=200)


def handle_room_availability(query, userID):
    db = _require_db()
    reservation_time_range = _require_reservation_time_range()
    room_id, room_data = find_room(query.get("room"))
    if not room_id:
        return https_fn.Response("강의실을 찾을 수 없습니다.", status=404)
    room_name = display_room_label(room_id, room_data)
    now = datetime.now(KST)
    one_day_later = now + timedelta(days=1)
    docs = db.collection("Reservations").where("roomID", "==", room_id).stream()
    times = []
    for doc in docs:
        data = doc.to_dict()
        if data.get("status") in {"취소", "거절"}:
            continue
        start, _ = reservation_time_range(data)
        if start and now <= start < one_day_later:
            times.append((start, data.get("startTime", "?")))
    times.sort(key=lambda item: item[0])
    if not times:
        return https_fn.Response(f"{room_name}은 앞으로 24시간 예약이 없습니다.", status=200)
    return https_fn.Response(f"{room_name} 예약 시간 목록: {', '.join(time for _, time in times)}", status=200)
