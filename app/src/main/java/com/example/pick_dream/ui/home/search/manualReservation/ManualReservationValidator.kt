package com.example.pick_dream.ui.home.search.manualReservation

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.util.ReservationTimeUtils

sealed interface ManualReservationSlotValidation {
    data object Ready : ManualReservationSlotValidation
    data object Loading : ManualReservationSlotValidation
    data class Invalid(val message: String) : ManualReservationSlotValidation
}

object ManualReservationValidator {
    fun validateSlot(
        year: Int?,
        month: Int?,
        day: Int?,
        startHour: Int?,
        startMinute: Int?,
        endHour: Int?,
        endMinute: Int?,
        existingReservations: List<Reservation>?
    ): ManualReservationSlotValidation {
        if (
            year == null || month == null || day == null ||
            startHour == null || startMinute == null ||
            endHour == null || endMinute == null
        ) {
            return ManualReservationSlotValidation.Invalid("날짜와 시간을 선택해 주세요")
        }
        if (existingReservations == null) return ManualReservationSlotValidation.Loading

        val start = ReservationTimeUtils.toReservationTimeString(
            year, month, day, startHour, startMinute
        )
        val end = ReservationTimeUtils.toReservationTimeString(
            year, month, day, endHour, endMinute
        )
        val startMillis = ReservationTimeUtils.parseReservationTimeMillis(start)
            ?: return ManualReservationSlotValidation.Invalid("예약 시작 시간을 확인해 주세요")
        val endMillis = ReservationTimeUtils.parseReservationTimeMillis(end)
            ?: return ManualReservationSlotValidation.Invalid("예약 종료 시간을 확인해 주세요")

        if (endMillis <= startMillis) {
            return ManualReservationSlotValidation.Invalid("종료 시간은 시작 시간 이후여야 합니다")
        }
        if (startMillis <= System.currentTimeMillis()) {
            return ManualReservationSlotValidation.Invalid("이미 지난 시간입니다")
        }
        if (ReservationTimeUtils.hasOverlap(startMillis, endMillis, existingReservations)) {
            return ManualReservationSlotValidation.Invalid("이미 예약된 시간입니다")
        }
        return ManualReservationSlotValidation.Ready
    }

    fun validateDetails(
        eventName: String,
        eventDescription: String,
        eventTarget: String,
        eventParticipants: Int,
        roomCapacity: Int?
    ): String? {
        if (
            eventName.isBlank() || eventDescription.isBlank() ||
            eventTarget.isBlank() || eventParticipants <= 0
        ) {
            return "행사명, 목적, 인원수, 참여대상을 모두 입력해주세요."
        }
        if (roomCapacity != null && eventParticipants > roomCapacity) {
            return "최대 수용 인원(${roomCapacity}명)을 초과할 수 없습니다."
        }
        return null
    }

    fun validateReservation(
        reservation: Reservation,
        existingReservations: List<Reservation>
    ): String? {
        val startMillis = ReservationTimeUtils.parseReservationTimeMillis(reservation.startTime)
            ?: return "예약 시작 시간을 확인할 수 없습니다."
        val endMillis = ReservationTimeUtils.parseReservationTimeMillis(reservation.endTime)
            ?: return "예약 종료 시간을 확인할 수 없습니다."
        if (endMillis <= startMillis) return "종료 시간은 시작 시간 이후여야 합니다."
        if (startMillis <= System.currentTimeMillis()) return "이미 지난 시간입니다."
        if (ReservationTimeUtils.hasOverlap(startMillis, endMillis, existingReservations)) {
            return "이미 예약된 시간입니다."
        }
        return null
    }
}
