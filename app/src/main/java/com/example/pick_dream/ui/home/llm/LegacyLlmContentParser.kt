package com.example.pick_dream.ui.home.llm

internal object LegacyLlmContentParser {
    fun parseCards(text: String): List<LlmCard> {
        val isReservationList = text.startsWith("현재 예약 및 예정된 예약:")
        val isCancelSelection = text.startsWith("취소할 예약을 선택해 주세요:")
        val isChangeSelection = text.startsWith("변경할 예약을 선택해 주세요:")
        if (!isReservationList && !isCancelSelection && !isChangeSelection) {
            parseConfirmationCard(text)?.let { return listOf(it) }
            parseAlternativeRoomCard(text)?.let { return listOf(it) }
            parseConflictCard(text)?.let { return listOf(it) }
            return emptyList()
        }

        return text
            .lineSequence()
            .drop(1)
            .map { it.trim() }
            .filter { it.startsWith("- ") && ":" in it && "~" in it }
            .mapNotNull { line ->
                val content = line.removePrefix("- ").trim()
                val roomName = content.substringBefore(":").trim()
                val rest = content.substringAfter(":", "").trim()
                if (roomName.isBlank() || rest.isBlank()) return@mapNotNull null

                val timeAndPeople = rest.split(" / ", limit = 2)
                val timeRange = timeAndPeople[0].split(" ~ ", limit = 2)
                if (timeRange.size != 2) return@mapNotNull null

                val action = when {
                    isCancelSelection -> LlmAction(
                        label = "예약 취소",
                        message = "$roomName ${simplifyKoreanDateTime(timeRange[0])} 예약 취소해줘",
                        displayText = "예약 취소"
                    )
                    isChangeSelection -> LlmAction(
                        label = "예약 변경",
                        message = "$roomName ${simplifyKoreanDateTime(timeRange[0])} 예약 변경해줘",
                        displayText = "예약 변경"
                    )
                    else -> null
                }

                LlmCard(
                    type = when {
                        isCancelSelection -> "cancel_selection_legacy"
                        isChangeSelection -> "change_selection_legacy"
                        else -> "reservation_summary_legacy"
                    },
                    roomName = roomName,
                    startTime = timeRange[0],
                    endTime = timeRange[1],
                    participants = timeAndPeople.getOrNull(1),
                    actions = listOfNotNull(action)
                )
            }
            .toList()
    }

    fun headerText(text: String): String {
        return when {
            text.startsWith("취소할 예약을 선택해 주세요:") -> "취소할 예약을 선택해 주세요"
            text.startsWith("변경할 예약을 선택해 주세요:") -> "변경할 예약을 선택해 주세요"
            text.startsWith("예약 내용을 확인해 주세요") -> "예약 내용을 확인해 주세요"
            "대신" in text && "예약 가능" in text -> "대체 강의실 제안"
            "이미" in text && "해당 시간" in text && "예약" in text -> "예약 충돌 안내"
            else -> "현재 예약 및 예정된 예약"
        }
    }

    fun parseQuickActions(text: String): List<LlmAction> {
        val actions = mutableListOf<LlmAction>()
        val normalized = text.replace(" ", "")
        val asksForConfirmation =
            ("예약확정" in normalized || "'예약확정'" in normalized) &&
                "예약되었습니다" !in normalized &&
                "변경되었습니다" !in normalized &&
                "취소되었습니다" !in normalized

        if (asksForConfirmation) {
            actions.add(LlmAction("예약 확정", "예약확정", "예약확정"))
        }

        val suggestsAlternative =
            "다른강의실" in normalized &&
                ("말해주세요" in normalized || "입력해주세요" in normalized || "찾아드릴" in normalized) &&
                "예약확정" !in normalized

        if (suggestsAlternative) {
            val isOwnReservationConflict =
                "새예약을추가로만들수는없어요" in normalized ||
                    "새예약을추가로만들수없어요" in normalized ||
                    "같은시간대에이미" in normalized ||
                    "예약해두셔서" in normalized ||
                    "예약해두셨어요" in normalized
            actions.add(
                LlmAction(
                    label = if (isOwnReservationConflict) "기존 예약 변경" else "다른 강의실 찾기",
                    message = if (isOwnReservationConflict) {
                        "기존 예약을 다른 강의실로 변경해줘"
                    } else {
                        "다른 강의실 찾아줘"
                    },
                    displayText = if (isOwnReservationConflict) "기존 예약 변경" else "다른 강의실 찾기"
                )
            )
        }
        return actions
    }

    private fun parseConfirmationCard(text: String): LlmCard? {
        if (!text.startsWith("예약 내용을 확인해 주세요")) return null
        val roomName = extractLineValue(text, "강의실") ?: return null
        val times = splitTimeRange(extractLineValue(text, "시간") ?: return null) ?: return null
        return LlmCard(
            type = "confirmation_legacy",
            roomName = roomName,
            startTime = times.first,
            endTime = times.second,
            participants = extractLineValue(text, "인원"),
            actions = listOf(LlmAction("예약 확정", "예약확정", "예약확정"))
        )
    }

    private fun parseAlternativeRoomCard(text: String): LlmCard? {
        if (!("대신" in text && "예약 가능" in text)) return null
        val roomName = Regex("""대신\s+(.+?)은\s+같은\s+시간에\s+예약\s+가능""")
            .find(text)?.groupValues?.getOrNull(1)?.trim() ?: return null
        val times = splitTimeRange(extractLineValue(text, "시간") ?: return null) ?: return null
        return LlmCard(
            type = "alternative_legacy",
            roomName = roomName,
            startTime = times.first,
            endTime = times.second,
            participants = extractLineValue(text, "인원"),
            actions = listOf(LlmAction("예약 확정", "예약확정", "예약확정"))
        )
    }

    private fun parseConflictCard(text: String): LlmCard? {
        if (!("이미" in text && "해당 시간" in text && "예약" in text)) return null
        val isOwnReservationConflict =
            "새 예약을 추가로 만들 수는 없어요" in text ||
                "새 예약을 추가로 만들 수 없어요" in text ||
                "같은 시간대에 이미" in text ||
                "예약해두셔서" in text ||
                "예약해두셨어요" in text
        val roomName = Regex("""이미\s+(.+?)을\(를\)\s+해당\s+시간""")
            .find(text)?.groupValues?.getOrNull(1)?.trim()
            ?: Regex("""이미\s+(.+?)은\s+해당\s+시간""")
                .find(text)?.groupValues?.getOrNull(1)?.trim()
            ?: Regex("""^(.+?)은\s+해당\s+시간""", RegexOption.MULTILINE)
                .find(text)?.groupValues?.getOrNull(1)?.trim()
            ?: return null
        return LlmCard(
            type = "conflict_legacy",
            roomName = roomName,
            description = if (isOwnReservationConflict) {
                "같은 시간대에 예약하신 기록이 있어요."
            } else {
                "해당 시간에 이미 예약되어 있어요."
            },
            actions = listOf(
                LlmAction(
                    label = if (isOwnReservationConflict) "기존 예약 변경" else "다른 강의실 찾기",
                    message = if (isOwnReservationConflict) {
                        "기존 예약을 다른 강의실로 변경해줘"
                    } else {
                        "다른 강의실 찾아줘"
                    },
                    displayText = if (isOwnReservationConflict) "기존 예약 변경" else "다른 강의실 찾기"
                )
            )
        )
    }

    private fun extractLineValue(text: String, label: String): String? {
        return text.lineSequence().map { it.trim() }
            .firstOrNull { it.startsWith("$label:") }
            ?.substringAfter(":")?.trim()?.takeIf { it.isNotBlank() }
    }

    private fun splitTimeRange(value: String): Pair<String, String>? {
        val parts = value.split(" ~ ", limit = 2)
        return if (parts.size == 2) parts[0].trim() to parts[1].trim() else null
    }

    private fun simplifyKoreanDateTime(value: String): String {
        return value
            .replace(Regex("\\s+\\d+초\\s+UTC\\+9"), "")
            .replace(Regex("\\s+UTC\\+9"), "")
            .trim()
    }
}
