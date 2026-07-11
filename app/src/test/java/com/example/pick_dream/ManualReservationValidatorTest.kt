package com.example.pick_dream

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.ui.home.search.manualReservation.ManualReservationSlotValidation
import com.example.pick_dream.ui.home.search.manualReservation.ManualReservationValidator
import com.example.pick_dream.util.ReservationTimeUtils
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ManualReservationValidatorTest {
    @Test
    fun futureAvailableSlotIsReady() {
        val result = ManualReservationValidator.validateSlot(
            year = 2099,
            month = 7,
            day = 12,
            startHour = 13,
            startMinute = 0,
            endHour = 15,
            endMinute = 0,
            existingReservations = emptyList()
        )

        assertTrue(result is ManualReservationSlotValidation.Ready)
    }

    @Test
    fun overlappingSlotIsRejected() {
        val existing = Reservation(
            roomID = "7202",
            startTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 12, 13, 0),
            endTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 12, 15, 0)
        )

        val result = ManualReservationValidator.validateSlot(
            year = 2099,
            month = 7,
            day = 12,
            startHour = 14,
            startMinute = 0,
            endHour = 16,
            endMinute = 0,
            existingReservations = listOf(existing)
        )

        assertEquals(
            "이미 예약된 시간입니다",
            (result as ManualReservationSlotValidation.Invalid).message
        )
    }

    @Test
    fun invalidOrOverCapacityDetailsAreRejected() {
        assertEquals(
            "행사명, 목적, 인원수, 참여대상을 모두 입력해주세요.",
            ManualReservationValidator.validateDetails("", "목적", "학생", 3, 30)
        )
        assertEquals(
            "최대 수용 인원(30명)을 초과할 수 없습니다.",
            ManualReservationValidator.validateDetails("행사", "목적", "학생", 31, 30)
        )
    }
}
