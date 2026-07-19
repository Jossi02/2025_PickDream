package com.example.pick_dream.util

import com.example.pick_dream.model.Reservation
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

object ReservationTimeUtils {
    private fun reservationTimeFormat() =
        SimpleDateFormat(
            "yyyy년 M월 d일 a h시 m분 s초 'UTC+9'",
            Locale.KOREA
        ).apply {
            isLenient = false
            timeZone = TimeZone.getTimeZone("Asia/Seoul")
        }

    fun toReservationTimeString(
        year: Int,
        month: Int,
        day: Int,
        hour24: Int,
        minute: Int
    ): String {
        val ampm = if (hour24 < 12) "오전" else "오후"
        val hour12 = when {
            hour24 == 0 -> 12
            hour24 > 12 -> hour24 - 12
            else -> hour24
        }

        return String.format(
            "%d년 %d월 %d일 %s %d시 %d분 0초 UTC+9",
            year,
            month,
            day,
            ampm,
            hour12,
            minute
        )
    }

    fun parseReservationTimeMillis(value: String?): Long? {
        if (value.isNullOrBlank()) return null
        return try {
            reservationTimeFormat().parse(value)?.time
        } catch (e: Exception) {
            null
        }
    }

    fun isStartTimeInPast(
        year: Int,
        month: Int,
        day: Int,
        startHour: Int,
        startMinute: Int,
        nowMillis: Long = System.currentTimeMillis()
    ): Boolean {
        val start = Calendar.getInstance(TimeZone.getTimeZone("Asia/Seoul")).apply {
            set(Calendar.YEAR, year)
            set(Calendar.MONTH, month - 1)
            set(Calendar.DAY_OF_MONTH, day)
            set(Calendar.HOUR_OF_DAY, startHour)
            set(Calendar.MINUTE, startMinute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        return start.timeInMillis <= nowMillis
    }

    fun overlaps(
        startMillis: Long,
        endMillis: Long,
        existingStartMillis: Long,
        existingEndMillis: Long
    ): Boolean {
        return startMillis < existingEndMillis && endMillis > existingStartMillis
    }

    fun hasOverlap(
        startMillis: Long,
        endMillis: Long,
        existingReservations: List<Reservation>
    ): Boolean {
        return existingReservations.any { reservation ->
            if (reservation.status == "취소" || reservation.status == "거절") return@any false

            val existingStart = parseReservationTimeMillis(reservation.startTime)
            val existingEnd = parseReservationTimeMillis(reservation.endTime)
            if (existingStart == null || existingEnd == null) return@any false

            overlaps(startMillis, endMillis, existingStart, existingEnd)
        }
    }
}
