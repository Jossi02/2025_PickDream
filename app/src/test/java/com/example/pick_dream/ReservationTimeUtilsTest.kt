package com.example.pick_dream

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.util.ReservationTimeUtils
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Calendar
import java.util.TimeZone

class ReservationTimeUtilsTest {
    @Test
    fun parsesKoreanReservationTime() {
        val millis = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오전 11시 0분 0초 UTC+9"
        )

        assertNotNull(millis)
    }

    @Test
    fun parsingUsesAsiaSeoulRegardlessOfDeviceTimezone() {
        val previousTimeZone = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
            val millis = ReservationTimeUtils.parseReservationTimeMillis(
                "2026년 7월 4일 오전 11시 0분 0초 UTC+9"
            )!!
            val seoul = Calendar.getInstance(TimeZone.getTimeZone("Asia/Seoul")).apply {
                timeInMillis = millis
            }

            assertEquals(11, seoul.get(Calendar.HOUR_OF_DAY))
        } finally {
            TimeZone.setDefault(previousTimeZone)
        }
    }

    @Test
    fun overlapAllowsTouchingBoundaries() {
        val start = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오전 11시 0분 0초 UTC+9"
        )!!
        val end = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 1시 0분 0초 UTC+9"
        )!!
        val nextStart = end
        val nextEnd = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 2시 0분 0초 UTC+9"
        )!!

        assertFalse(ReservationTimeUtils.overlaps(nextStart, nextEnd, start, end))
    }

    @Test
    fun overlapDetectsPartialOverlap() {
        val existingStart = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오전 11시 0분 0초 UTC+9"
        )!!
        val existingEnd = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 1시 0분 0초 UTC+9"
        )!!
        val newStart = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 12시 0분 0초 UTC+9"
        )!!
        val newEnd = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 2시 0분 0초 UTC+9"
        )!!

        assertTrue(ReservationTimeUtils.overlaps(newStart, newEnd, existingStart, existingEnd))
    }

    @Test
    fun hasOverlapIgnoresCanceledAndRejectedReservations() {
        val newStart = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오전 11시 30분 0초 UTC+9"
        )!!
        val newEnd = ReservationTimeUtils.parseReservationTimeMillis(
            "2026년 7월 4일 오후 12시 30분 0초 UTC+9"
        )!!
        val existing = listOf(
            Reservation(
                startTime = "2026년 7월 4일 오전 11시 0분 0초 UTC+9",
                endTime = "2026년 7월 4일 오후 1시 0분 0초 UTC+9",
                status = "취소"
            ),
            Reservation(
                startTime = "2026년 7월 4일 오전 11시 0분 0초 UTC+9",
                endTime = "2026년 7월 4일 오후 1시 0분 0초 UTC+9",
                status = "거절"
            )
        )

        assertFalse(ReservationTimeUtils.hasOverlap(newStart, newEnd, existing))
    }

    @Test
    fun startTimeInPastUsesProvidedNowMillis() {
        val now = Calendar.getInstance().apply {
            set(2026, Calendar.JULY, 4, 12, 0, 0)
            set(Calendar.MILLISECOND, 0)
        }.timeInMillis

        assertTrue(ReservationTimeUtils.isStartTimeInPast(2026, 7, 4, 11, 59, now))
        assertFalse(ReservationTimeUtils.isStartTimeInPast(2026, 7, 4, 12, 1, now))
    }
}
