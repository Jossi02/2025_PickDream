from datetime import datetime
import re

from reservation_utils import (
    KST,
    extract_room_id,
    parse_natural_korean_datetime,
)


def is_reservation_confirmation(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    if "예약해" in normalized and "예약확정" not in normalized:
        return False
    robust_confirmation_words = (
        "\uc608\uc57d\ud655\uc815",
        "\ud655\uc815",
        "\ud655\uc778\ud588\uc5b4",
        "\uc9c4\ud589\ud574",
        "\uc9c4\ud589",
        "\uadf8\uac78\ub85c",
        "\uadf8\uac83\uc73c\ub85c",
        "\uc88b\uc544",
        "\uc751",
        "\ub124",
        "\ub9de\uc544",
        "ok",
        "okay",
    )
    robust_cancellation_words = (
        "\ucde8\uc18c",
        "\uc544\ub2c8",
        "\ub9d0\uace0",
        "\ubcc0\uacbd",
        "\ubc14\uafd4",
    )
    if any(word in normalized for word in robust_confirmation_words) and not any(
        word in normalized for word in robust_cancellation_words
    ):
        return True
    confirmation_words = (
        "예약확정",
        "확정",
        "확인했어",
        "진행해",
        "진행",
        "그걸로",
        "그대로",
        "좋아",
        "네",
        "응",
        "맞아",
        "오케이",
        "ok",
        "okay",
    )
    cancellation_words = ("취소", "아니", "말고", "변경", "바꿔")
    return any(word in normalized for word in confirmation_words) and not any(
        word in normalized for word in cancellation_words
    )


def is_alternative_room_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\ub2e4\ub978\uac15\uc758\uc2e4",
            "\ub2e4\ub978\ubc29",
            "\ub2e4\ub978\uacf3",
            "\ub2e4\ub978\ub370",
            "\ub300\uccb4\uac15\uc758\uc2e4",
            "\ub300\uccb4\ub85c",
            "\ube48\uac15\uc758\uc2e4",
            "\uac00\ub2a5\ud55c\uac15\uc758\uc2e4",
        )
    )


def is_cancel_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc608\uc57d\ucde8\uc18c",
            "\uc608\uc57d\uc744\ucde8\uc18c",
            "\ucde8\uc18c\ud574",
            "\ucde8\uc18c\ud574\uc918",
            "\ucde8\uc18c\ud558\uace0\uc2f6",
            "\ucde8\uc18c\ud560\uac8c",
            "\uc608\uc57d\uc0ad\uc81c",
            "\uc608\uc57d\uc5c6\uc560",
        )
    )


def is_change_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    if is_cancel_reservation_request(normalized):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc608\uc57d\ubcc0\uacbd",
            "\ubcc0\uacbd\ud558\uace0\uc2f6",
            "\ubcc0\uacbd\ud574",
            "\ubcc0\uacbd\ud574\uc918",
            "\ubc14\uafb8\uace0\uc2f6",
            "\ubc14\uafd4\uc918",
            "\ubc14\uafd4",
            "\uc2dc\uac04\ubc14",
            "\uc2dc\uac04\uc744\ubc14",
            "\uc778\uc6d0\ubc14",
            "\uc778\uc6d0\uc218\ubcc0\uacbd",
            "\uc778\uc6d0\uc744\ubcc0\uacbd",
            "\uba85\uc73c\ub85c\ubc14",
            "\uac15\uc758\uc2e4\ubc14",
        )
    )


def is_explicit_change_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uae30\uc874\uc608\uc57d",
            "\ub0b4\uc608\uc57d",
            "\uc608\uc57d\ubcc0\uacbd",
            "\uc608\uc57d\uc744\ubcc0\uacbd",
            "\uc608\uc57d\ubc14",
            "\ubcc0\uacbd\ud574",
            "\ubcc0\uacbd\ud574\uc918",
            "\ubc14\uafd4\uc918",
            "\ubc14\uafd4",
        )
    )


def is_my_reservations_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    if is_change_reservation_request(normalized) or is_cancel_reservation_request(normalized):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\ub0b4\uc608\uc57d",
            "\uc608\uc57d\ub0b4\uc5ed",
            "\uc608\uc57d\ud655\uc778",
            "\uc608\uc57d\uc870\ud68c",
            "\uc608\uc57d\ubcf4\uc5ec",
            "\ubb50\uc608\uc57d",
        )
    ) and not is_reservation_confirmation(normalized)


def is_new_reservation_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\uc0c8\ub85c\uc6b4\uc608\uc57d",
            "\uc0c8\uc608\uc57d",
            "\uc2e0\uaddc\uc608\uc57d",
            "\uc0c8\ub85c\uc608\uc57d",
            "\ub2e4\uc2dc\uc608\uc57d",
            "\ucc98\uc74c\ubd80\ud130",
        )
    )


def is_reservation_request_text(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    if is_recommendation_or_lookup_request(text):
        return False
    return any(
        word in normalized
        for word in (
            "\uc608\uc57d",
            "\ub300\uc5ec",
            "\ube4c\ub824",
            "\uc0ac\uc6a9",
            "\uc7a1\uc544",
        )
    )


def is_recommendation_or_lookup_request(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "\ucd94\ucc9c",
            "\uc54c\ub824\uc918",
            "\ucc3e\uc544\uc918",
            "\uc870\ud68c",
            "\uc5b4\ub514\uc57c",
            "\uc5b4\ub514\uc5d0",
            "\uc788\ub294\uac15\uc758\uc2e4",
            "\uc788\ub294\ubc29",
            "\uc774\uc6a9\ud558\uae30\uc88b\uc740",
            "\uc608\uc57d\uac00\ub2a5\ud55c",
            "\uac00\ub2a5\ud55c\uac15\uc758\uc2e4",
        )
    )


def parse_participant_count(text):
    if not text:
        return None
    match = re.search(r"(?<!\d)(\d{1,3})\s*(?:\uba85|\uc0ac\ub78c|\uc778)(?!\d)", str(text))
    if match:
        return int(match.group(1))
    normalized = str(text).strip()
    if re.fullmatch(r"\d{1,3}", normalized):
        return int(normalized)
    return None


def parse_duration_hours(text):
    if not text:
        return None
    raw = str(text)
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:\uc2dc\uac04|hours?|h)(?!\d)", raw, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def enrich_query_from_direct_parse(query, room_id=None, start=None, participants=None, duration=None):
    if room_id and not query.get("room"):
        query["room"] = room_id
    if start and not query.get("startTime"):
        query["startTime"] = start.isoformat()
    if participants is not None and not query.get("eventParticipants"):
        query["eventParticipants"] = str(participants)
    if duration is not None and not query.get("duration"):
        query["duration"] = duration
    return query


def recover_reserve_fields_from_text(query, raw_text, now=None):
    if not raw_text:
        return query

    now = now or datetime.now(KST)
    if not query.get("room"):
        room_id = extract_room_id(raw_text)
        if room_id:
            query["room"] = room_id

    if not query.get("startTime"):
        start = parse_natural_korean_datetime(raw_text, now)
        if start:
            query["startTime"] = start.isoformat()

    if not query.get("eventParticipants"):
        participants = parse_participant_count(raw_text)
        if participants is not None:
            query["eventParticipants"] = str(participants)

    if not query.get("duration"):
        duration = parse_duration_hours(raw_text)
        if duration is not None:
            query["duration"] = duration

    return query


def extract_recommendation_keywords(text):
    raw = str(text or "")
    normalized = re.sub(r"\s+", "", raw).lower()
    keywords = []
    equipment_aliases = {
        "마이크": ("마이크", "mic", "microphone"),
        "빔프로젝터": ("빔프로젝터", "프로젝터", "beam", "projector"),
        "프로젝터": ("빔프로젝터", "프로젝터", "beam", "projector"),
        "콘센트": ("콘센트", "전원", "전기"),
        "스크린": ("스크린", "screen"),
        "화이트보드": ("화이트보드", "보드", "칠판"),
        "전자칠판": ("전자칠판", "전자칠판"),
        "에어컨": ("에어컨", "냉방"),
    }
    for canonical, aliases in equipment_aliases.items():
        if any(alias.lower() in normalized for alias in aliases):
            if canonical not in keywords:
                keywords.append(canonical)
    if "\uc9c0\uae08" in normalized:
        keywords.append("\uc9c0\uae08")
    participant_count = parse_participant_count(raw)
    if participant_count is not None:
        keywords.append(f"{participant_count}\uba85")
    return keywords


def extract_room_ids(text):
    if not text:
        return []
    found = []
    for match in re.finditer(r"(?<!\d)([1-9]\d{3})(?!\d)", str(text)):
        room_id = match.group(1)
        if room_id not in found:
            found.append(room_id)
    single = extract_room_id(text)
    if single and single not in found:
        found.insert(0, single)
    return found
